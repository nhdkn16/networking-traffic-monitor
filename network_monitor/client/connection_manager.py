import asyncio
import logging
from typing import Callable, Optional, Dict, Any
from network_monitor.client.api_client import ApiClient
from network_monitor.client.websocket_client import WebSocketClient

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Quản lý phối hợp giữa HTTP REST API Client và WebSocket Client."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.api_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}/ws"
        self.api_client: Optional[ApiClient] = None
        self.ws_client: Optional[WebSocketClient] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._was_connected_before = False

    async def resync_state(self) -> Optional[Dict[str, Any]]:
        """Gọi HTTP REST API để đồng bộ lại thông tin sau khi kết nối lại."""
        if not self.api_client:
            self.api_client = ApiClient(self.api_url)
        try:
            health = await self.api_client.check_health()
            interfaces = await self.api_client.get_interfaces()
            return {"health": health, "interfaces": interfaces}
        except Exception as e:
            logger.warning(f"Lỗi khi resync dữ liệu từ HTTP API: {e}")
            return None

    async def connect(
        self,
        on_message: Callable[[Dict[str, Any]], None],
        on_status_change: Callable[[str, str], None],
        on_resync: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> bool:
        """Thực hiện kiểm tra HTTP API và thiết lập luồng WebSocket."""
        self.api_client = ApiClient(self.api_url)
        try:
            health = await self.api_client.check_health()
            on_status_change("http_ok", f"HTTP API sẵn sàng (Trạng thái: {health.get('status')})")
        except Exception as e:
            on_status_change("http_error", f"Không thể kết nối HTTP API: {e}")
            await self.api_client.close()
            self.api_client = None
            return False

        self.ws_client = WebSocketClient(self.ws_url)

        async def handle_ws_status_async(status: str, msg: str) -> None:
            if status == "connected":
                if self._was_connected_before and on_resync:
                    on_status_change("resyncing", "Đang đồng bộ lại trạng thái từ Server...")
                    resync_data = await self.resync_state()
                    if resync_data and on_resync:
                        on_resync(resync_data)
                self._was_connected_before = True
            on_status_change(f"ws_{status}", msg)

        def handle_ws_status(status: str, msg: str) -> None:
            asyncio.create_task(handle_ws_status_async(status, msg))

        self._listen_task = asyncio.create_task(
            self.ws_client.connect_and_listen(on_message, handle_ws_status)
        )
        return True

    async def disconnect(self) -> None:
        """Ngắt tất cả kết nối."""
        self._was_connected_before = False
        if self.ws_client:
            await self.ws_client.disconnect()
            self.ws_client = None
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listen_task = None
        if self.api_client:
            await self.api_client.close()
            self.api_client = None
            