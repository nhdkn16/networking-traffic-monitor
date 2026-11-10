"""HTTP routes của Server (CLAUDE.md mục 3.1)."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from network_monitor.models.schemas import (
    AlertEvent,
    AlertRule,
    AnalyticsSummary,
    CaptureStatus,
    HealthResponse,
    InterfaceListResponse,
    PacketMetadata,
    TrafficSample,
)
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
ws_router = APIRouter()

def get_service(request: Request) -> MonitoringService:
    return request.app.state.service


def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager


@router.get("/health", response_model=HealthResponse)
async def get_health(
    service: MonitoringService = Depends(get_service),
    ws_manager: WebSocketManager = Depends(get_ws_manager),
) -> HealthResponse:

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
    try:
        interfaces = service.list_interfaces(include_all=include_all)
        
    except Exception:  # noqa: BLE001
        
        logger.exception("Không đọc được danh sách interface")
        raise HTTPException(status_code=500, detail="Không đọc được danh sách interface") from None    
    return InterfaceListResponse(monitored_interface=service.interface, interfaces=interfaces)


@router.get("/statistics/current", response_model=TrafficSample)
async def get_current_statistics(
    service: MonitoringService = Depends(get_service),
) -> TrafficSample:

    sample = service.latest_sample()
    if sample is None:
        last_error = service.last_error
        if last_error:
            detail = f"Chưa có dữ liệu lưu lượng: {last_error}"
        else:
            detail = "Chưa có dữ liệu lưu lượng: đang đo mẫu đầu tiên, hãy thử lại sau ít giây."
        raise HTTPException(status_code=503, detail=detail, headers={"Retry-After": "1"})
    return sample

# --- Endpoints cho Packet Capture (Giai đoạn 8) ---

@router.post("/capture/start", response_model=CaptureStatus)
def start_capture(
    interface: str | None = Query(default=None),
    service: MonitoringService = Depends(get_service),
) -> CaptureStatus:

    success = service.start_capture(interface=interface)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Không thể bắt đầu capture (Interface không hợp lệ hoặc thiếu quyền Administrator)",
        )

    return service.capture_status()


@router.post("/capture/stop", response_model=CaptureStatus)
def stop_capture(
    service: MonitoringService = Depends(get_service),
) -> CaptureStatus:
    service.stop_capture()

    return service.capture_status()

@router.get("/capture/status", response_model=CaptureStatus)
def get_capture_status(
    service: MonitoringService = Depends(get_service),
) -> CaptureStatus:
    
    return service.capture_status()


@router.get("/capture/packets", response_model=list[PacketMetadata])
def get_recent_packets(
    limit: int = Query(default=50, ge=1, le=500),
    service: MonitoringService = Depends(get_service),
) -> list[PacketMetadata]:

    return service.recent_packets(limit=limit)

# --- Endpoints mới cho Giai đoạn 9 (Analytics & Alerts) ---

@router.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    top_n: int = Query(default=5, ge=1, le=20),
    service: MonitoringService = Depends(get_service),
) -> AnalyticsSummary:

    return service.get_analytics_summary(top_n=top_n)


@router.post("/alerts/config", response_model=AlertRule)
def update_alert_config(
    rule: AlertRule,
    service: MonitoringService = Depends(get_service),
) -> AlertRule:
    service.update_alert_rule(rule)

    return service.get_alert_rule()

@router.get("/alerts/config", response_model=AlertRule)
def get_alert_config(
    service: MonitoringService = Depends(get_service),
) -> AlertRule:

    return service.get_alert_rule()

@router.get("/alerts/history", response_model=list[AlertEvent])
def get_alert_history(
    limit: int = Query(default=50, ge=1, le=200),
    service: MonitoringService = Depends(get_service),
) -> list[AlertEvent]:

    return service.get_alert_history(limit=limit)

# --- WebSocket Endpoint ---

@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    service: MonitoringService = websocket.app.state.service
    manager: WebSocketManager = websocket.app.state.ws_manager
    await websocket.accept()

    hello = build_message(TYPE_SERVER_STATUS, service.status_data().model_dump(mode="json"))
    result = await manager.connect(websocket, hello)
    if result == CONNECT_FULL:
        await websocket.close(code=CLOSE_TRY_AGAIN_LATER, reason="Server đã đạt giới hạn số Client")
        return
    if result != CONNECT_OK:
        return

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if not await manager.send(websocket, reply_to_client_message(message.get("text"))):
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("Lỗi không mong đợi trên kết nối WebSocket")
    finally:
        manager.unregister(websocket)
        