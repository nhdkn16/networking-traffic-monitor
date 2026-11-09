"""Quản lý kết nối WebSocket: đăng ký Client, broadcast, dọn Client chết hoặc quá chậm.

Quy ước message (CLAUDE.md mục 3.2 và 8): mọi message có dạng
``{"type": ..., "timestamp": "...Z", "data": {...}}``.

Chính sách Client chậm: mỗi lần gửi có timeout; quá hạn hoặc lỗi thì ngắt Client đó, không giữ
hàng đợi vô hạn. Các Client được gửi song song nên một Client chậm không làm chậm Client khác,
nhưng một lượt broadcast chỉ kết thúc khi Client chậm nhất hết timeout hoặc gửi xong.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TYPE_SERVER_STATUS = "server_status"
TYPE_TRAFFIC_UPDATE = "traffic_update"
TYPE_PONG = "pong"
TYPE_ERROR = "error"

CONNECT_OK = "ok"
CONNECT_FULL = "full"
CONNECT_FAILED = "failed"

MAX_CLIENT_MESSAGE_CHARS = 4096
CLOSE_GOING_AWAY = 1001
CLOSE_INTERNAL_ERROR = 1011
CLOSE_TRY_AGAIN_LATER = 1013


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_message(
    message_type: str, data: dict[str, Any], timestamp: datetime | None = None
) -> dict[str, Any]:
    """Tạo message theo định dạng chung; ``timestamp`` mặc định là thời điểm hiện tại (UTC)."""
    moment = timestamp if timestamp is not None else datetime.now(timezone.utc)
    return {"type": message_type, "timestamp": _iso_utc(moment), "data": data}


def error_message(code: str, message: str) -> dict[str, Any]:
    return build_message(TYPE_ERROR, {"code": code, "message": message})


def reply_to_client_message(text: str | None) -> dict[str, Any]:
    """Tạo phản hồi cho một message do Client gửi lên (hiện chỉ hỗ trợ ``ping``).

    Không trả lại nội dung do Client gửi để tránh phản chiếu dữ liệu tùy ý.
    """
    if text is None:
        return error_message("binary_not_supported", "Chỉ hỗ trợ message văn bản JSON")
    if len(text) > MAX_CLIENT_MESSAGE_CHARS:
        return error_message(
            "message_too_large", f"Message vượt quá {MAX_CLIENT_MESSAGE_CHARS} ký tự"
        )
    try:
        payload = json.loads(text)
    except ValueError:
        return error_message("invalid_json", "Message không phải JSON hợp lệ")
    if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
        return error_message("invalid_message", "Message phải là đối tượng JSON có trường 'type'")
    if payload["type"] == "ping":
        return build_message(TYPE_PONG, {})
    return error_message("unknown_type", "Loại message không được hỗ trợ (chỉ có 'ping')")


@dataclass(frozen=True)
class ConnectionInfo:
    client_id: str
    remote: str
    connected_at: datetime


@dataclass
class _Connection:
    info: ConnectionInfo
    websocket: Any
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # Tuần tự hóa việc gửi cho một Client


class WebSocketManager:
    def __init__(
        self,
        *,
        max_clients: int = 20,
        send_timeout: float = 2.0,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self._max_clients = max_clients
        self._send_timeout = send_timeout
        self._now = now_func or (lambda: datetime.now(timezone.utc))
        self._connections: dict[Any, _Connection] = {}

    @property
    def client_count(self) -> int:
        return len(self._connections)

    def clients(self) -> list[ConnectionInfo]:
        """Ảnh chụp danh sách Client đang kết nối (dùng cho Server GUI sau này)."""
        return [conn.info for conn in self._connections.values()]

    async def connect(self, websocket: Any, hello: dict[str, Any]) -> str:
        """Đăng ký Client và gửi message chào đầu tiên.

        Trả về ``CONNECT_FULL`` nếu đã đạt giới hạn (Client chưa được đăng ký, chưa nhận gì),
        ``CONNECT_FAILED`` nếu không gửi được message chào, ngược lại ``CONNECT_OK``.
        Message chào luôn đến trước mọi broadcast vì khóa gửi được giữ suốt lúc gửi.
        """
        if len(self._connections) >= self._max_clients:
            logger.warning("Từ chối kết nối WebSocket: đã đạt giới hạn %d Client", self._max_clients)
            return CONNECT_FULL
        client = getattr(websocket, "client", None)
        remote = f"{client.host}:{client.port}" if client is not None else "không rõ"
        conn = _Connection(
            info=ConnectionInfo(uuid.uuid4().hex[:8], remote, self._now()), websocket=websocket
        )
        # Thêm vào danh sách và lấy khóa không có điểm chờ giữa hai bước (khóa đang rảnh).
        self._connections[websocket] = conn
        async with conn.lock:
            delivered = await self._send_locked(conn, hello)
        if not delivered:
            return CONNECT_FAILED
        logger.info(
            "Client %s kết nối từ %s (đang có %d Client)",
            conn.info.client_id,
            remote,
            len(self._connections),
        )
        return CONNECT_OK

    def unregister(self, websocket: Any) -> None:
        """Gỡ Client khỏi danh sách (gọi lại nhiều lần vẫn an toàn)."""
        conn = self._connections.pop(websocket, None)
        if conn is not None:
            logger.info(
                "Client %s đã ngắt kết nối (còn %d Client)",
                conn.info.client_id,
                len(self._connections),
            )

    async def send(self, websocket: Any, message: dict[str, Any]) -> bool:
        """Gửi cho một Client; trả về False nếu Client không còn hoặc gửi thất bại."""
        conn = self._connections.get(websocket)
        if conn is None:
            return False
        return await self._send_to(conn, message)

    async def broadcast(self, message: dict[str, Any]) -> int:
        """Gửi cho mọi Client song song; trả về số Client nhận thành công."""
        connections = list(self._connections.values())
        if not connections:
            return 0
        results = await asyncio.gather(*(self._send_to(conn, message) for conn in connections))
        return sum(1 for delivered in results if delivered)

    async def close_all(self, code: int = CLOSE_GOING_AWAY, reason: str = "Server đang tắt") -> None:
        connections = list(self._connections.values())
        self._connections.clear()
        await asyncio.gather(*(self._close_quietly(conn, code, reason) for conn in connections))

    async def _send_to(self, conn: _Connection, message: dict[str, Any]) -> bool:
        async with conn.lock:
            if conn.websocket not in self._connections:
                return False  # Đã bị gỡ trong lúc chờ khóa
            return await self._send_locked(conn, message)

    async def _send_locked(self, conn: _Connection, message: dict[str, Any]) -> bool:
        try:
            await asyncio.wait_for(conn.websocket.send_json(message), timeout=self._send_timeout)
            return True
        except Exception as exc:  # noqa: BLE001 - ranh giới I/O: Client lỗi/chậm không được làm hỏng Server
            reason = "quá chậm" if isinstance(exc, asyncio.TimeoutError) else "gửi thất bại"
            logger.warning("Ngắt Client %s: %s (%r)", conn.info.client_id, reason, exc)
            self._connections.pop(conn.websocket, None)
            await self._close_quietly(conn, CLOSE_INTERNAL_ERROR, "Gửi dữ liệu thất bại hoặc quá chậm")
            return False

    @staticmethod
    async def _close_quietly(conn: _Connection, code: int, reason: str) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(conn.websocket.close(code=code, reason=reason), timeout=1.0)
