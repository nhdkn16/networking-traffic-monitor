import asyncio
import logging
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QThread, pyqtSignal
from network_monitor.client.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class ClientWorker(QThread):
    """QThread chạy asyncio loop riêng để xử lý giao tiếp mạng độc lập với GUI thread."""

    status_changed = pyqtSignal(str, str)
    traffic_updated = pyqtSignal(dict)
    server_status_updated = pyqtSignal(dict)
    resynced = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    packets_captured = pyqtSignal(list)
    capture_status_changed = pyqtSignal(dict)
    analytics_updated = pyqtSignal(dict)
    alert_history_updated = pyqtSignal(list)       # Signal mới: Danh sách cảnh báo
    alert_config_received = pyqtSignal(dict)       # Signal mới: Cấu hình Alert hiện tại

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.manager: Optional[ConnectionManager] = None
        self._should_stop = False
        self._is_capturing = False

    def run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._async_run())
        self.loop.close()

    async def _async_run(self) -> None:
        self.manager = ConnectionManager(self.host, self.port)

        def on_ws_message(msg: Dict[str, Any]) -> None:
            msg_type = msg.get("type")
            if msg_type == "traffic_update":
                self.traffic_updated.emit(msg.get("data", {}))
            elif msg_type == "server_status":
                self.server_status_updated.emit(msg.get("data", {}))
            elif msg_type == "error":
                err_msg = msg.get("data", {}).get("message", "Lỗi WebSocket từ Server")
                self.log_message.emit(f"[LỖI SERVER] {err_msg}")

        def on_status_change(status_code: str, message: str) -> None:
            self.status_changed.emit(status_code, message)
            self.log_message.emit(f"[{status_code.upper()}] {message}")

        def on_resync(resync_data: Dict[str, Any]) -> None:
            self.resynced.emit(resync_data)
            self.log_message.emit("[ĐỒNG BỘ LẠI] Đã khôi phục và đồng bộ xong dữ liệu từ HTTP REST API!")

        success = await self.manager.connect(on_ws_message, on_status_change, on_resync)
        if not success:
            return

        # Đọc cấu hình Alert ban đầu
        try:
            cfg = await self.manager.api_client.get_alert_config()
            self.alert_config_received.emit(cfg)
        except Exception as e:
            logger.debug(f"Không lấy được cấu hình Alert: {e}")

        poll_counter = 0
        while not self._should_stop:
            await asyncio.sleep(0.5)
            poll_counter += 1

            if self.manager and self.manager.api_client and poll_counter % 2 == 0:
                try:
                    # Poll lịch sử cảnh báo mỗi 1 giây
                    alerts = await self.manager.api_client.get_alert_history(limit=50)
                    self.alert_history_updated.emit(alerts)

                    if self._is_capturing:
                        packets = await self.manager.api_client.get_recent_packets(limit=100)
                        self.packets_captured.emit(packets)

                        status = await self.manager.api_client.get_capture_status()
                        self.capture_status_changed.emit(status)

                        analytics = await self.manager.api_client.get_analytics_summary(top_n=5)
                        self.analytics_updated.emit(analytics)
                except Exception as e:
                    logger.debug(f"Lỗi poll data: {e}")

        await self.manager.disconnect()

    def set_alert_config_request(self, rule_data: Dict[str, Any]) -> None:
        """Gửi cấu hình Alert xuống Server."""
        if self.loop and self.manager and self.manager.api_client:
            asyncio.run_coroutine_threadsafe(self._async_set_alert_config(rule_data), self.loop)

    async def _async_set_alert_config(self, rule_data: Dict[str, Any]) -> None:
        try:
            cfg = await self.manager.api_client.set_alert_config(rule_data)
            self.alert_config_received.emit(cfg)
            self.log_message.emit("[ALERT CONFIG] Đã cập nhật cấu hình ngưỡng cảnh báo thành công!")
        except Exception as e:
            self.log_message.emit(f"[LỖI ALERT CONFIG] Không thể cập nhật cấu hình cảnh báo: {e}")

    def start_capture_request(self, interface: Optional[str] = None) -> None:
        if self.loop and self.manager and self.manager.api_client:
            asyncio.run_coroutine_threadsafe(self._async_start_capture(interface), self.loop)

    def stop_capture_request(self) -> None:
        if self.loop and self.manager and self.manager.api_client:
            asyncio.run_coroutine_threadsafe(self._async_stop_capture(), self.loop)

    async def _async_start_capture(self, interface: Optional[str]) -> None:
        try:
            status = await self.manager.api_client.start_capture(interface)
            self._is_capturing = status.get("is_running", False)
            self.capture_status_changed.emit(status)
            self.log_message.emit(f"[CAPTURE] Đã bật bắt gói tin trên interface: {status.get('interface')}")
        except Exception as e:
            self.log_message.emit(f"[LỖI CAPTURE] Không thể bật capture: {e}")

    async def _async_stop_capture(self) -> None:
        try:
            status = await self.manager.api_client.stop_capture()
            self._is_capturing = False
            self.capture_status_changed.emit(status)
            self.log_message.emit("[CAPTURE] Đã dừng bắt gói tin.")
        except Exception as e:
            self.log_message.emit(f"[LỖI CAPTURE] Không thể dừng capture: {e}")

    def stop(self) -> None:
        self._should_stop = True
        