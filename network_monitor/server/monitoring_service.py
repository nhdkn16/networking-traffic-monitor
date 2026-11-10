"""MonitoringService: vòng lấy mẫu nền, giữ mẫu lưu lượng mới nhất."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from network_monitor import APP_NAME, __version__
from network_monitor.config import Settings
from network_monitor.core.alert_engine import AlertEngine
from network_monitor.core.analyzer import TrafficAnalyzer
from network_monitor.core.collector import (
    InterfaceDownError,
    InterfaceNotFoundError,
    NetworkCollector,
)
from network_monitor.core.sniffer import PacketSniffer
from network_monitor.models.schemas import (
    AlertEvent,
    AlertRule,
    AnalyticsSummary,
    CaptureStatus,
    InterfaceInfo,
    PacketMetadata,
    ServerStatusData,
    TrafficSample,
)

logger = logging.getLogger(__name__)

SampleListener = Callable[[TrafficSample], Awaitable[None]]
StatusListener = Callable[[], Awaitable[None]]
AlertListener = Callable[[list[AlertEvent]], Awaitable[None]]


class NoInterfaceError(RuntimeError):
    """Không có interface nào phù hợp để giám sát."""


class MonitoringService:
    def __init__(self, collector: NetworkCollector, settings: Settings) -> None:
        self._collector = collector
        self._settings = settings
        self._pinned = settings.interface is not None
        self._interface: str | None = settings.interface
        self._latest: TrafficSample | None = None
        self._last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._created_at = time.monotonic()
        self._sample_listeners: list[SampleListener] = []
        self._status_listeners: list[StatusListener] = []
        self._alert_listeners: list[AlertListener] = []

        # Tích hợp PacketSniffer, AlertEngine cho Giai đoạn 8 & 9
        self._sniffer = PacketSniffer()
        self._alert_engine = AlertEngine()

    # --- Đăng ký listener ---

    def add_sample_listener(self, listener: SampleListener) -> None:
        self._sample_listeners.append(listener)

    def add_status_listener(self, listener: StatusListener) -> None:
        self._status_listeners.append(listener)

    def add_alert_listener(self, listener: AlertListener) -> None:
        self._alert_listeners.append(listener)

    # --- Analytics & Alert APIs (Giai đoạn 9) ---

    def get_analytics_summary(self, top_n: int = 5) -> AnalyticsSummary:
        packets = self._sniffer.get_recent_packets(limit=1000)
        return TrafficAnalyzer.analyze(packets, top_n=top_n)

    def update_alert_rule(self, rule: AlertRule) -> None:
        self._alert_engine.update_rule(rule)

    def get_alert_rule(self) -> AlertRule:
        return self._alert_engine.rule

    def get_alert_history(self, limit: int = 50) -> list[AlertEvent]:
        return self._alert_engine.get_history(limit=limit)

    # --- Packet Sniffer APIs (Giai đoạn 8) ---

    def start_capture(self, interface: str | None = None) -> bool:
        target = interface or self._interface or self._collector.default_interface()
        if not target:
            return False
        return self._sniffer.start(target)

    def stop_capture(self) -> None:
        self._sniffer.stop()

    def capture_status(self) -> CaptureStatus:
        return self._sniffer.get_status()

    def recent_packets(self, limit: int = 100) -> list[PacketMetadata]:
        return self._sniffer.get_recent_packets(limit=limit)

    # --- Trạng thái (chỉ đọc) ---

    @property
    def settings(self) -> Settings:
        return self._settings

    def status_data(self) -> ServerStatusData:
        return ServerStatusData(
            status="degraded" if self._last_error else "ok",
            app_name=APP_NAME,
            version=__version__,
            monitored_interface=self._interface,
            sample_interval_seconds=self._settings.sample_interval_seconds,
            last_error=self._last_error,
        )

    @property
    def interface(self) -> str | None:
        return self._interface

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._created_at

    def latest_sample(self) -> TrafficSample | None:
        return self._latest

    def list_interfaces(self, include_all: bool = False) -> list[InterfaceInfo]:
        return self._collector.list_interfaces(include_all=include_all)

    # --- Vòng đời ---

    async def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.create_task(self._run(), name="monitoring-sampler")
        logger.info("Đã bắt đầu vòng lấy mẫu (chu kỳ %.2fs)", self._settings.sample_interval_seconds)

    async def stop(self) -> None:
        self.stop_capture()
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("Đã dừng vòng lấy mẫu")

    async def _run(self) -> None:
        while True:
            await self.sample_once()
            await asyncio.sleep(self._settings.sample_interval_seconds)

    # --- Một lần lấy mẫu ---

    async def sample_once(self) -> None:
        try:
            interface, sample = await asyncio.to_thread(self._sample_blocking, self._interface)
        except Exception as exc:  # noqa: BLE001
            if self._handle_failure(exc):
                await self._notify(self._status_listeners)
            return
        self._interface = interface
        if self._set_error(None):
            await self._notify(self._status_listeners)
        if sample.upload_bytes_per_second is not None and sample.download_bytes_per_second is not None:
            self._latest = sample
            await self._notify(self._sample_listeners, sample)

            # Kiểm tra ngưỡng cảnh báo (AlertEngine)
            alerts = self._alert_engine.check_sample(sample)
            if alerts:
                await self._notify(self._alert_listeners, alerts)

    async def _notify(self, listeners: list[Any], *args: Any) -> None:
        for listener in list(listeners):
            try:
                await listener(*args)
            except Exception:  # noqa: BLE001
                logger.exception("Listener bị lỗi")

    def _sample_blocking(self, interface: str | None) -> tuple[str, TrafficSample]:
        if interface is None:
            interface = self._collector.default_interface()
            if interface is None:
                raise NoInterfaceError("Không tìm thấy interface đang hoạt động")
        self._collector.ensure_interface_up(interface)
        return interface, self._collector.sample(interface)

    def _handle_failure(self, exc: Exception) -> bool:
        self._latest = None
        self._collector.reset()
        if isinstance(exc, (NoInterfaceError, InterfaceNotFoundError, InterfaceDownError)):
            message = str(exc)
            if isinstance(exc, (InterfaceNotFoundError, InterfaceDownError)) and not self._pinned:
                self._interface = None
            return self._set_error(message)
        return self._set_error(f"Lỗi khi đọc lưu lượng: {exc}", exc_info=exc)

    def _set_error(self, message: str | None, exc_info: BaseException | None = None) -> bool:
        if message == self._last_error:
            return False
        if message is None:
            logger.info("Việc lấy mẫu đã hoạt động lại bình thường")
        else:
            logger.warning(message, exc_info=exc_info)
        self._last_error = message
        return True
    