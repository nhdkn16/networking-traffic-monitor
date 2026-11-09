"""Khởi tạo ứng dụng FastAPI và chạy Server bằng Uvicorn."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from network_monitor import APP_NAME, __version__
from network_monitor.config import Settings
from network_monitor.core.collector import NetworkCollector
from network_monitor.models.schemas import TrafficSample
from network_monitor.server.monitoring_service import MonitoringService
from network_monitor.server.routes import router, ws_router
from network_monitor.server.websocket_manager import (
    TYPE_SERVER_STATUS,
    TYPE_TRAFFIC_UPDATE,
    WebSocketManager,
    build_message,
)


def create_app(
    settings: Settings | None = None,
    *,
    service: MonitoringService | None = None,
    autostart: bool = True,
) -> FastAPI:
    """Tạo ứng dụng FastAPI.

    ``service`` và ``autostart`` cho phép kiểm thử đưa vào dịch vụ đã dựng sẵn và tắt vòng nền.
    Mỗi lần gọi hàm này đăng ký thêm listener lên ``service``, nên không dùng chung một service
    cho nhiều ứng dụng.
    """
    if service is None:
        service = MonitoringService(NetworkCollector(), settings or Settings.from_env())
    manager = WebSocketManager(max_clients=service.settings.max_ws_clients)

    async def broadcast_sample(sample: TrafficSample) -> None:
        data = sample.model_dump(mode="json", exclude={"timestamp"})
        await manager.broadcast(build_message(TYPE_TRAFFIC_UPDATE, data, sample.timestamp))

    async def broadcast_status() -> None:
        data = service.status_data().model_dump(mode="json")
        await manager.broadcast(build_message(TYPE_SERVER_STATUS, data))

    service.add_sample_listener(broadcast_sample)
    service.add_status_listener(broadcast_status)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if autostart:
            await service.start()
        try:
            yield
        finally:
            await service.stop()  # Dừng phát dữ liệu trước rồi mới đóng kết nối
            await manager.close_all()

    app = FastAPI(title=f"{APP_NAME} API", version=__version__, lifespan=lifespan)
    app.state.service = service
    app.state.ws_manager = manager
    app.include_router(router)
    app.include_router(ws_router)
    return app


def run_server(settings: Settings) -> None:
    """Chạy Server (blocking) cho đến khi nhận Ctrl+C."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
