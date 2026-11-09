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
    """Một mẫu lưu lượng của một interface.

    ``upload_bytes_per_second`` và ``download_bytes_per_second`` là tốc độ trung bình
    kể từ lần lấy mẫu trước của cùng interface. Giá trị ``None`` nghĩa là CHƯA ĐO ĐƯỢC
    (lần đọc đầu tiên, chưa có mốc so sánh), không phải 0.
    """

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
    """Phản hồi của GET /api/health.

    ``status`` là "ok" khi dịch vụ lấy mẫu hoạt động bình thường và "degraded" khi đang có lỗi
    (ví dụ không tìm thấy interface); HTTP Server vẫn chạy trong cả hai trường hợp.
    """

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
