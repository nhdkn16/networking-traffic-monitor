"""Kiểm thử WebSocketManager và các hàm xử lý message.

Dùng đối tượng WebSocket GIẢ (không có mạng) chỉ để kiểm tra logic; endpoint /ws thật được
kiểm thử trong test_websocket.py.
"""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from network_monitor.server.websocket_manager import (
    CONNECT_FAILED,
    CONNECT_FULL,
    CONNECT_OK,
    MAX_CLIENT_MESSAGE_CHARS,
    WebSocketManager,
    build_message,
    reply_to_client_message,
)


class FakeWebSocket:
    def __init__(self, *, delay: float = 0.0, fail: bool = False, client=None) -> None:
        self.sent: list[dict] = []
        self.delay = delay
        self.fail = fail
        self.closed_with: tuple[int, str] | None = None
        self.client = client

    async def send_json(self, message: dict) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("kết nối đã đóng")
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = (code, reason)


def _msg(text: str = "x") -> dict:
    return build_message("traffic_update", {"v": text})


# --- build_message / reply_to_client_message ---


def test_build_message_envelope_and_utc_format() -> None:
    moment = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
    message = build_message("traffic_update", {"a": 1}, moment)
    assert message == {"type": "traffic_update", "timestamp": "2026-01-01T10:30:00Z", "data": {"a": 1}}


def test_reply_ping_returns_pong() -> None:
    reply = reply_to_client_message(json.dumps({"type": "ping"}))
    assert reply["type"] == "pong"
    assert reply["data"] == {}


def test_reply_errors() -> None:
    cases = {
        None: "binary_not_supported",
        "khong phai json": "invalid_json",
        json.dumps([1, 2]): "invalid_message",
        json.dumps({"no_type": 1}): "invalid_message",
        json.dumps({"type": 5}): "invalid_message",
        json.dumps({"type": "lenh_la"}): "unknown_type",
        "x" * (MAX_CLIENT_MESSAGE_CHARS + 1): "message_too_large",
    }
    for text, code in cases.items():
        reply = reply_to_client_message(text)
        assert reply["type"] == "error", text
        assert reply["data"]["code"] == code, text


def test_reply_does_not_echo_client_content() -> None:
    reply = reply_to_client_message(json.dumps({"type": "BI-MAT-12345"}))
    assert "BI-MAT-12345" not in json.dumps(reply)


# --- WebSocketManager ---


def test_connect_sends_hello_and_registers() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        ws = FakeWebSocket(client=SimpleNamespace(host="192.168.56.101", port=50000))
        assert await manager.connect(ws, _msg("hello")) == CONNECT_OK
        assert manager.client_count == 1
        assert ws.sent[0]["data"] == {"v": "hello"}
        assert manager.clients()[0].remote == "192.168.56.101:50000"

    asyncio.run(scenario())


def test_connect_rejected_when_full() -> None:
    async def scenario() -> None:
        manager = WebSocketManager(max_clients=1)
        first, second = FakeWebSocket(), FakeWebSocket()
        assert await manager.connect(first, _msg()) == CONNECT_OK
        assert await manager.connect(second, _msg()) == CONNECT_FULL
        assert manager.client_count == 1
        assert second.sent == []  # Client bị từ chối không nhận gì

    asyncio.run(scenario())


def test_connect_failed_when_hello_cannot_be_sent() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        ws = FakeWebSocket(fail=True)
        assert await manager.connect(ws, _msg()) == CONNECT_FAILED
        assert manager.client_count == 0
        assert ws.closed_with is not None

    asyncio.run(scenario())


def test_broadcast_reaches_all_clients() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        a, b = FakeWebSocket(), FakeWebSocket()
        await manager.connect(a, _msg("hello"))
        await manager.connect(b, _msg("hello"))
        delivered = await manager.broadcast(_msg("update"))
        assert delivered == 2
        assert a.sent[-1]["data"] == {"v": "update"}
        assert b.sent[-1]["data"] == {"v": "update"}

    asyncio.run(scenario())


def test_broadcast_with_no_clients_returns_zero() -> None:
    assert asyncio.run(WebSocketManager().broadcast(_msg())) == 0


def test_broadcast_drops_failing_client_and_keeps_others() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        good, bad = FakeWebSocket(), FakeWebSocket()
        await manager.connect(good, _msg("hello"))
        await manager.connect(bad, _msg("hello"))
        bad.fail = True  # Từ giờ gửi cho Client này sẽ lỗi
        delivered = await manager.broadcast(_msg("update"))
        assert delivered == 1
        assert manager.client_count == 1
        assert good.sent[-1]["data"] == {"v": "update"}
        assert bad.closed_with is not None and bad.closed_with[0] == 1011

    asyncio.run(scenario())


def test_broadcast_drops_slow_client_without_delaying_others() -> None:
    async def scenario() -> None:
        manager = WebSocketManager(send_timeout=0.05)
        fast, slow = FakeWebSocket(), FakeWebSocket()
        await manager.connect(fast, _msg("hello"))
        await manager.connect(slow, _msg("hello"))
        slow.delay = 0.5  # Chậm hơn timeout
        delivered = await manager.broadcast(_msg("update"))
        assert delivered == 1
        assert manager.client_count == 1
        assert fast.sent[-1]["data"] == {"v": "update"}
        assert all(m["data"] != {"v": "update"} for m in slow.sent)

    asyncio.run(scenario())


def test_hello_is_delivered_before_concurrent_broadcast() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        ws = FakeWebSocket(delay=0.05)
        connect_task = asyncio.create_task(manager.connect(ws, _msg("hello")))
        await asyncio.sleep(0)  # Cho connect() bắt đầu và đăng ký Client
        await manager.broadcast(_msg("update"))
        await connect_task
        assert [m["data"]["v"] for m in ws.sent] == ["hello", "update"]

    asyncio.run(scenario())


def test_unregister_is_idempotent() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        ws = FakeWebSocket()
        await manager.connect(ws, _msg())
        manager.unregister(ws)
        manager.unregister(ws)
        assert manager.client_count == 0
        assert await manager.send(ws, _msg()) is False

    asyncio.run(scenario())


def test_close_all_closes_every_client() -> None:
    async def scenario() -> None:
        manager = WebSocketManager()
        a, b = FakeWebSocket(), FakeWebSocket()
        await manager.connect(a, _msg())
        await manager.connect(b, _msg())
        await manager.close_all()
        assert manager.client_count == 0
        assert a.closed_with is not None and a.closed_with[0] == 1001
        assert b.closed_with is not None and b.closed_with[0] == 1001

    asyncio.run(scenario())
