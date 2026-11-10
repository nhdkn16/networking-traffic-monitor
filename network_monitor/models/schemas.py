"""Các model dữ liệu dùng chung giữa Collector, Server và Client.

Quy ước đơn vị (CLAUDE.md mục 8):
- ``*_bytes``: số byte tích lũy.
- ``*_bytes_per_second``: byte mỗi giây (1 byte = 8 bit).
- ``timestamp``: ISO 8601, có múi giờ UTC.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class InterfaceInfo(BaseModel):
    """Thông tin tĩnh của một network interface trên Host."""

    model_config = ConfigDict(frozen=True)

    name: str
    is_up: bool
    is_loopback: bool
    speed_mbps: int  # Tốc độ liên kết theo Mbps; 0 nghĩa là không xác định
    mtu: int
    ipv4_addresses: list[str]


class InterfaceCounters(BaseModel):
    """Bộ đếm tích lũy của một interface tại một thời điểm đọc."""

    model_config = ConfigDict(frozen=True)

    sent_bytes: int
    received_bytes: int
    sent_packets: int
    received_packets: int


class TrafficSample(BaseModel):
    """Một mẫu lưu lượng của một interface."""

    model_config = ConfigDict(frozen=True)

    interface: str
    timestamp: datetime
    total_sent_bytes: int
    total_received_bytes: int
    total_sent_packets: int
    total_received_packets: int
    upload_bytes_per_second: float | None = None
    download_bytes_per_second: float | None = None


class HealthResponse(BaseModel):
    """Phản hồi của GET /api/health."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    app_name: str
    version: str
    server_time: datetime
    uptime_seconds: float
    monitored_interface: str | None = None
    last_error: str | None = None
    websocket_clients: int = 0


class InterfaceListResponse(BaseModel):
    """Phản hồi của GET /api/interfaces."""

    model_config = ConfigDict(frozen=True)

    monitored_interface: str | None = None
    interfaces: list[InterfaceInfo]


class ServerStatusData(BaseModel):
    """Trạng thái Server; dùng làm ``data`` của message WebSocket ``server_status``."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    app_name: str
    version: str
    monitored_interface: str | None = None
    sample_interval_seconds: float
    last_error: str | None = None


# --- Giai đoạn 8: Packet Capture Schemas ---


class PacketMetadata(BaseModel):
    """Metadata gói tin trích xuất qua Scapy."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    src_ip: str
    dst_ip: str
    src_port: int | None = None
    dst_port: int | None = None
    protocol: str
    length_bytes: int
    process_name: str | None = None
    process_id: int | None = None


class CaptureStatus(BaseModel):
    """Trạng thái tiến trình Packet Capture."""

    model_config = ConfigDict(frozen=True)

    is_running: bool
    interface: str | None = None
    packet_count: int = 0
    error_message: str | None = None


# --- Giai đoạn 9: Analytics & Alert Schemas ---


class ProtocolDistribution(BaseModel):
    """Thống kê số lượng và tỷ lệ % theo từng giao thức."""

    model_config = ConfigDict(frozen=True)

    protocol: str
    packet_count: int
    percentage: float


class TopTalkerItem(BaseModel):
    """Thông tin IP tiêu thụ băng thông nhiều nhất."""

    model_config = ConfigDict(frozen=True)

    ip: str
    total_bytes: int
    packet_count: int


class AnalyticsSummary(BaseModel):
    """Tổng hợp phân tích giao thức và Top Talkers."""

    model_config = ConfigDict(frozen=True)

    total_packets_analyzed: int
    protocols: list[ProtocolDistribution]
    top_senders: list[TopTalkerItem]
    top_receivers: list[TopTalkerItem]


class AlertRule(BaseModel):
    """Cấu hình ngưỡng cảnh báo lưu lượng mạng."""

    model_config = ConfigDict(frozen=False)

    max_upload_bytes_per_sec: float | None = None
    max_download_bytes_per_sec: float | None = None
    enabled: bool = True


class AlertEvent(BaseModel):
    """Sự kiện cảnh báo khi tốc độ lưu lượng vượt ngưỡng."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    alert_type: str  # "upload_exceeded" | "download_exceeded"
    metric_name: str
    current_value: float
    threshold_value: float
    message: str
    