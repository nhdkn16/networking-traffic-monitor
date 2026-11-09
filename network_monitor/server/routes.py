"""HTTP routes của Server (CLAUDE.md mục 3.1)."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from network_monitor.models.schemas import HealthResponse, InterfaceListResponse, TrafficSample
from network_monitor.server.monitoring_service import MonitoringService
from network_monitor.server.websocket_manager import (
    CLOSE_TRY_AGAIN_LATER,
    CONNECT_FULL,
    CONNECT_OK,
    TYPE_SERVER_STATUS,
    WebSocketManager,
    build_message,
    reply_to_client_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
ws_router = APIRouter()  # Không có tiền tố: đường dẫn WebSocket là /ws (CLAUDE.md mục 3.2)


def get_service(request: Request) -> MonitoringService:
    return request.app.state.service


def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager


@router.get("/health", response_model=HealthResponse)
async def get_health(
    service: MonitoringService = Depends(get_service),
    ws_manager: WebSocketManager = Depends(get_ws_manager),
) -> HealthResponse:
    """Kiểm tra tình trạng Server."""
    status = service.status_data()
    return HealthResponse(
        status=status.status,
        app_name=status.app_name,
        version=status.version,
        server_time=datetime.now(timezone.utc),
        uptime_seconds=service.uptime_seconds(),
        monitored_interface=status.monitored_interface,
        last_error=status.last_error,
        websocket_clients=ws_manager.client_count,
    )


@router.get("/interfaces", response_model=InterfaceListResponse)
def get_interfaces(
    include_all: bool = False, service: MonitoringService = Depends(get_service)
) -> InterfaceListResponse:
    """Danh sách interface trên Host. Mặc định bỏ qua loopback và interface đang ngắt kết nối."""
    try:
        interfaces = service.list_interfaces(include_all=include_all)
    except Exception:  # noqa: BLE001 - ranh giới I/O
        logger.exception("Không đọc được danh sách interface")
        raise HTTPException(status_code=500, detail="Không đọc được danh sách interface") from None
    return InterfaceListResponse(monitored_interface=service.interface, interfaces=interfaces)


@router.get("/statistics/current", response_model=TrafficSample)
async def get_current_statistics(
    service: MonitoringService = Depends(get_service),
) -> TrafficSample:
    """Mẫu lưu lượng mới nhất của interface đang giám sát."""
    sample = service.latest_sample()
    if sample is None:
        last_error = service.last_error
        if last_error:
            detail = f"Chưa có dữ liệu lưu lượng: {last_error}"
        else:
            detail = "Chưa có dữ liệu lưu lượng: đang đo mẫu đầu tiên, hãy thử lại sau ít giây."
        raise HTTPException(status_code=503, detail=detail, headers={"Retry-After": "1"})
    return sample


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Kênh đẩy dữ liệu thời gian thực: server_status, traffic_update; nhận ping và trả pong."""
    service: MonitoringService = websocket.app.state.service
    manager: WebSocketManager = websocket.app.state.ws_manager
    await websocket.accept()

    hello = build_message(TYPE_SERVER_STATUS, service.status_data().model_dump(mode="json"))
    result = await manager.connect(websocket, hello)
    if result == CONNECT_FULL:
        await websocket.close(code=CLOSE_TRY_AGAIN_LATER, reason="Server đã đạt giới hạn số Client")
        return
    if result != CONNECT_OK:
        return  # Manager đã gỡ và đóng kết nối này

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if not await manager.send(websocket, reply_to_client_message(message.get("text"))):
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - ranh giới I/O: không để lỗi một kết nối lan ra ngoài
        logger.exception("Lỗi không mong đợi trên kết nối WebSocket")
    finally:
        manager.unregister(websocket)
