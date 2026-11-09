"""MonitoringService: vòng lấy mẫu nền, giữ mẫu lưu lượng mới nhất.

Lý do dùng vòng nền thay vì tính tốc độ theo từng request: nếu mỗi lần gọi API lại lấy mẫu
thì tốc độ phụ thuộc tần suất các Client gọi và nhiều Client sẽ làm nhiễu nhau. Ở đây chỉ một
tác vụ nền lấy mẫu theo chu kỳ cố định; HTTP (và sau này WebSocket) chỉ đọc mẫu mới nhất.

Không đưa số liệu giả: khi chưa có mẫu có tốc độ, hoặc khi đọc lỗi, ``latest_sample()`` trả về
``None`` thay vì giữ lại dữ liệu cũ.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from network_monitor import APP_NAME, __version__
from network_monitor.config import Settings
from network_monitor.core.collector import InterfaceNotFoundError, NetworkCollector
from network_monitor.models.schemas import InterfaceInfo, ServerStatusData, TrafficSample

logger = logging.getLogger(__name__)

SampleListener = Callable[[TrafficSample], Awaitable[None]]
StatusListener = Callable[[], Awaitable[None]]


class NoInterfaceError(RuntimeError):
    """Không có interface nào phù hợp để giám sát."""


class MonitoringService:
    def __init__(self, collector: NetworkCollector, settings: Settings) -> None:
        self._collector = collector
        self._settings = settings
        self._pinned = settings.interface is not None  # Người dùng chỉ định interface cố định
        self._interface: str | None = settings.interface
        self._latest: TrafficSample | None = None
        self._last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._created_at = time.monotonic()
        self._sample_listeners: list[SampleListener] = []
        self._status_listeners: list[StatusListener] = []

    # --- Đăng ký listener ---

    def add_sample_listener(self, listener: SampleListener) -> None:
        """Gọi ``listener(sample)`` mỗi khi có mẫu mới có tốc độ (không gọi cho mốc ban đầu)."""
        self._sample_listeners.append(listener)

    def add_status_listener(self, listener: StatusListener) -> None:
        """Gọi ``listener()`` mỗi khi ``last_error`` thay đổi (trạng thái ok/degraded)."""
        self._status_listeners.append(listener)

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
        """Mẫu mới nhất có tốc độ; ``None`` nếu chưa có hoặc đang lỗi."""
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
        """Lấy một mẫu. Công việc blocking của psutil chạy trong thread để không chặn event loop."""
        try:
            interface, sample = await asyncio.to_thread(self._sample_blocking, self._interface)
        except Exception as exc:  # noqa: BLE001 - ranh giới I/O: lỗi không được làm chết vòng nền
            if self._handle_failure(exc):
                await self._notify(self._status_listeners)
            return
        self._interface = interface
        if self._set_error(None):
            await self._notify(self._status_listeners)
        if sample.upload_bytes_per_second is not None and sample.download_bytes_per_second is not None:
            self._latest = sample
            await self._notify(self._sample_listeners, sample)
        # Ngược lại đây mới chỉ là mốc so sánh ban đầu: chưa công bố mẫu nào.

    async def _notify(self, listeners: list[Any], *args: Any) -> None:
        """Gọi lần lượt các listener; lỗi của một listener không được làm hỏng vòng lấy mẫu."""
        for listener in list(listeners):
            try:
                await listener(*args)
            except Exception:  # noqa: BLE001 - ranh giới listener
                logger.exception("Listener bị lỗi")

    def _sample_blocking(self, interface: str | None) -> tuple[str, TrafficSample]:
        if interface is None:
            interface = self._collector.default_interface()
            if interface is None:
                raise NoInterfaceError("Không tìm thấy interface đang hoạt động")
        return interface, self._collector.sample(interface)

    def _handle_failure(self, exc: Exception) -> bool:
        """Xử lý lỗi lấy mẫu; trả về True nếu ``last_error`` thay đổi."""
        self._latest = None  # Không giữ dữ liệu cũ như thể còn mới
        self._collector.reset()  # Lần đo lại sau lỗi phải bắt đầu từ mốc mới
        if isinstance(exc, (NoInterfaceError, InterfaceNotFoundError)):
            message = str(exc)
            if isinstance(exc, InterfaceNotFoundError) and not self._pinned:
                self._interface = None  # Chế độ tự chọn: lần sau chọn lại interface
            return self._set_error(message)
        return self._set_error(f"Lỗi khi đọc lưu lượng: {exc}", exc_info=exc)

    def _set_error(self, message: str | None, exc_info: BaseException | None = None) -> bool:
        """Đặt trạng thái lỗi; trả về True nếu có thay đổi."""
        if message == self._last_error:
            return False  # Chỉ ghi log khi trạng thái thay đổi, tránh lặp mỗi chu kỳ
        if message is None:
            logger.info("Việc lấy mẫu đã hoạt động lại bình thường")
        else:
            logger.warning(message, exc_info=exc_info)
        self._last_error = message
        return True
