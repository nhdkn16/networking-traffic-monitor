import asyncio
import json
import logging
from typing import Callable, Optional, Dict, Any
import websockets

logger = logging.getLogger(__name__)

class WebSocketClient:
    """Client WebSocket với cơ chế tự động kết nối lại (reconnect backoff)."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._running = False
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None

    async def connect_and_listen(
        self,
        on_message: Callable[[Dict[str, Any]], None],
        on_status_change: Callable[[str, str], None],
    ) -> None:
        """Vòng lặp duy trì kết nối WebSocket và nhận dữ liệu liên tục."""
        self._running = True
        retry_delay = 1.0
        max_delay = 15.0
        retry_count = 0

        while self._running:
            try:
                if retry_count > 0:
                    on_status_change("connecting", f"Đang kết nối lại (lần {retry_count})...")
                else:
                    on_status_change("connecting", "Đang kết nối WebSocket...")

                async with websockets.connect(self.ws_url) as ws:
                    self._websocket = ws
                    retry_count = 0
                    retry_delay = 1.0  # Reset delay khi kết nối thành công
                    on_status_change("connected", "Đã kết nối WebSocket realtime")

                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            on_message(data)
                        except json.JSONDecodeError:
                            logger.warning("Nhận message không phải JSON hợp lệ từ WebSocket")

            except (websockets.exceptions.WebSocketException, OSError, asyncio.CancelledError) as e:
                if not self._running:
                    break
                retry_count += 1
                msg = f"Ngắt kết nối WebSocket ({e}). Thử lại sau {retry_delay:.1f}s (lần {retry_count})..."
                logger.warning(msg)
                on_status_change("disconnected", msg)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_delay)

        on_status_change("disconnected", "Đã ngắt kết nối WebSocket")

    async def send_ping(self) -> None:
        """Gửi message ping đến Server."""
        if self._websocket and self._websocket.open:
            await self._websocket.send(json.dumps({"type": "ping"}))

    async def disconnect(self) -> None:
        """Dừng kết nối WebSocket."""
        self._running = False
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
            