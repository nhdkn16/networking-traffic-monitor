"""Cấu hình tập trung của Network Monitor.

Giá trị mặc định có thể bị ghi đè bằng biến môi trường (xem các hằng ENV_*) hoặc tham số
dòng lệnh. Không lưu mật khẩu, token hay secret trong file này.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

ENV_HOST = "NETWORK_MONITOR_HOST"
ENV_PORT = "NETWORK_MONITOR_PORT"
ENV_INTERVAL = "NETWORK_MONITOR_INTERVAL"
ENV_INTERFACE = "NETWORK_MONITOR_INTERFACE"
ENV_MAX_WS_CLIENTS = "NETWORK_MONITOR_MAX_WS_CLIENTS"

# Mặc định chỉ lắng nghe trên máy Host vì API chưa có xác thực.
# Muốn Guest truy cập, chạy: python main.py server --host 0.0.0.0
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_MAX_WS_CLIENTS = 20


@dataclass(frozen=True)
class Settings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    sample_interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    interface: str | None = None  # None = tự chọn interface mặc định
    max_ws_clients: int = DEFAULT_MAX_WS_CLIENTS  # Số Client WebSocket tối đa cùng lúc

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("host không được để trống")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"port phải nằm trong khoảng 1-65535, nhận được {self.port}")
        if self.sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds phải lớn hơn 0")
        if self.interface is not None and not self.interface.strip():
            raise ValueError("interface không được là chuỗi rỗng")
        if self.max_ws_clients < 1:
            raise ValueError("max_ws_clients phải lớn hơn hoặc bằng 1")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Đọc cấu hình từ biến môi trường; biến chưa đặt hoặc rỗng thì dùng mặc định."""
        env = os.environ if environ is None else environ
        kwargs: dict[str, object] = {}
        if host := env.get(ENV_HOST):
            kwargs["host"] = host
        if raw_port := env.get(ENV_PORT):
            try:
                kwargs["port"] = int(raw_port)
            except ValueError:
                raise ValueError(f"Biến môi trường {ENV_PORT} không hợp lệ: {raw_port!r}") from None
        if raw_interval := env.get(ENV_INTERVAL):
            try:
                kwargs["sample_interval_seconds"] = float(raw_interval)
            except ValueError:
                raise ValueError(
                    f"Biến môi trường {ENV_INTERVAL} không hợp lệ: {raw_interval!r}"
                ) from None
        if interface := env.get(ENV_INTERFACE):
            kwargs["interface"] = interface
        if raw_max := env.get(ENV_MAX_WS_CLIENTS):
            try:
                kwargs["max_ws_clients"] = int(raw_max)
            except ValueError:
                raise ValueError(
                    f"Biến môi trường {ENV_MAX_WS_CLIENTS} không hợp lệ: {raw_max!r}"
                ) from None
        return cls(**kwargs)
