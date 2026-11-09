"""Kiểm thử endpoint /ws bằng TestClient.

Collector giả (mock) chỉ phục vụ kiểm tra logic. Nếu một test có vẻ bị treo quá ~10 giây
(đang chờ một message không bao giờ đến), hãy nhấn Ctrl+C và báo lại.
"""
# Các helper dưới đây được dùng lại từ test_collector và test_api để tránh trùng lặp.
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from network_monitor.config import Settings
from network_monitor.core.collector import NetworkCollector
from network_monitor.server.main import create_app
from network_monitor.server.monitoring_service import MonitoringService
from tests.test_api import _primed_service
from tests.test_collector import _fake_host


def _live_service(max_ws_clients: int = 20) -> tuple[MonitoringService, dict]:
    """Service dùng đồng hồ thật để vòng nền tự công bố mẫu; ``state['up']`` bật/tắt interface."""
    state = {"up": True}
    io, addrs, stats = _fake_host()
    collector = NetworkCollector(
        io_counters_func=lambda: dict(io) if state["up"] else {},
        if_addrs_func=lambda: addrs,
        if_stats_func=lambda: stats,
    )
    settings = Settings(sample_interval_seconds=0.05, max_ws_clients=max_ws_clients)
    return MonitoringService(collector, settings), state


def _receive_until(ws, predicate, max_messages: int = 200) -> dict:
    for _ in range(max_messages):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("Không nhận được message mong đợi")


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_ws_sends_server_status_on_connect() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    with client.websocket_connect("/ws") as ws:
        message = ws.receive_json()
    assert message["type"] == "server_status"
    datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))
    assert message["data"]["status"] == "ok"
    assert message["data"]["monitored_interface"] == "Wi-Fi"
    assert message["data"]["sample_interval_seconds"] == 1.0


def test_ws_ping_returns_pong() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # server_status
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_ws_invalid_messages_return_error_and_keep_connection() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_text("khong phai json")
        assert ws.receive_json()["data"]["code"] == "invalid_json"
        ws.send_json({"type": "lenh_la"})
        assert ws.receive_json()["data"]["code"] == "unknown_type"
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["data"]["code"] == "binary_not_supported"
        ws.send_text("x" * 5000)
        assert ws.receive_json()["data"]["code"] == "message_too_large"
        ws.send_json({"type": "ping"})  # Kết nối vẫn dùng được sau các lỗi
        assert ws.receive_json()["type"] == "pong"


def test_ws_client_count_in_health_and_cleanup() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    assert client.get("/api/health").json()["websocket_clients"] == 0
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        assert client.get("/api/health").json()["websocket_clients"] == 1
    assert _wait_until(lambda: client.get("/api/health").json()["websocket_clients"] == 0)


def test_ws_rejects_clients_over_limit() -> None:
    service, _state = _live_service(max_ws_clients=1)
    client = TestClient(create_app(service=service, autostart=False))
    with client.websocket_connect("/ws") as first:
        first.receive_json()
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws") as second:
                second.receive_json()
        assert exc_info.value.code == 1013
        assert client.get("/api/health").json()["websocket_clients"] == 1


def test_ws_receives_traffic_updates_from_sampler() -> None:
    service, _state = _live_service()
    with TestClient(create_app(service=service, autostart=True)) as client:
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "server_status"
            update = _receive_until(ws, lambda m: m["type"] == "traffic_update")
    data = update["data"]
    assert data["interface"] == "Wi-Fi"
    assert isinstance(data["upload_bytes_per_second"], float)
    assert isinstance(data["download_bytes_per_second"], float)
    assert "timestamp" not in data  # timestamp nằm ở lớp bao ngoài
    datetime.fromisoformat(update["timestamp"].replace("Z", "+00:00"))


def test_ws_status_change_is_broadcast() -> None:
    service, state = _live_service()
    with TestClient(create_app(service=service, autostart=True)) as client:
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "server_status"
            _receive_until(ws, lambda m: m["type"] == "traffic_update")

            state["up"] = False  # interface biến mất
            degraded = _receive_until(
                ws, lambda m: m["type"] == "server_status" and m["data"]["status"] == "degraded"
            )
            assert degraded["data"]["last_error"]

            state["up"] = True  # interface quay lại
            _receive_until(
                ws, lambda m: m["type"] == "server_status" and m["data"]["status"] == "ok"
            )
            _receive_until(ws, lambda m: m["type"] == "traffic_update")
