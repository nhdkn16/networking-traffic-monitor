"""Collector: đọc bộ đếm lưu lượng của các network interface trên Host bằng psutil.

Collector chỉ đọc thống kê (counters), không bắt gói tin. Các hàm của psutil và
đồng hồ có thể được truyền vào khi khởi tạo để kiểm thử logic mà không phụ thuộc máy thật.
Lớp này không dùng chung giữa nhiều thread nếu không có khóa riêng; các thao tác trên
mốc so sánh tốc độ đã được bảo vệ bằng một khóa nội bộ.
"""

import ipaddress
import socket
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import psutil

from network_monitor.models.schemas import InterfaceCounters, InterfaceInfo, TrafficSample


class InterfaceNotFoundError(LookupError):
    """Interface được yêu cầu không có trong bộ đếm của hệ thống."""


class InterfaceDownError(RuntimeError):
    """Interface tồn tại nhưng đang ở trạng thái không hoạt động (DOWN)."""


def compute_rate(previous_bytes: int, current_bytes: int, elapsed_seconds: float) -> float:
    """Tính tốc độ (byte/giây) giữa hai lần đọc bộ đếm.

    Nếu bộ đếm giảm (card mạng bị reset), coi lượng byte tăng thêm là 0 thay vì trả về số âm.
    """
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds phải lớn hơn 0")
    delta = current_bytes - previous_bytes
    if delta < 0:
        return 0.0
    return delta / elapsed_seconds


def _extract_ipv4(addresses: list[Any]) -> list[str]:
    result: list[str] = []
    for entry in addresses:
        if entry.family != socket.AF_INET:
            continue
        try:
            result.append(str(ipaddress.IPv4Address(entry.address)))
        except ValueError:
            continue
    return result


def _is_loopback(name: str, ipv4_addresses: list[str]) -> bool:
    lowered = name.lower()
    if lowered == "lo" or lowered.startswith("loopback"):
        return True
    return any(ipaddress.IPv4Address(addr).is_loopback for addr in ipv4_addresses)


class NetworkCollector:
    """Liệt kê interface và lấy mẫu lưu lượng theo từng interface."""

    def __init__(
        self,
        *,
        io_counters_func: Callable[[], dict[str, Any]] | None = None,
        if_addrs_func: Callable[[], dict[str, list[Any]]] | None = None,
        if_stats_func: Callable[[], dict[str, Any]] | None = None,
        monotonic_func: Callable[[], float] | None = None,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self._io_counters = io_counters_func or (lambda: psutil.net_io_counters(pernic=True))
        self._if_addrs = if_addrs_func or psutil.net_if_addrs
        self._if_stats = if_stats_func or psutil.net_if_stats
        self._monotonic = monotonic_func or time.monotonic
        self._now = now_func or (lambda: datetime.now(timezone.utc))
        self._baselines: dict[str, tuple[float, InterfaceCounters]] = {}
        self._lock = threading.Lock()

    def list_interfaces(self, include_all: bool = False) -> list[InterfaceInfo]:
        """Liệt kê interface, sắp xếp theo tên.

        Mặc định bỏ qua loopback và interface đang ngắt kết nối; ``include_all=True`` liệt kê tất cả.
        """
        addrs = self._if_addrs()
        stats = self._if_stats()
        result: list[InterfaceInfo] = []
        for name in sorted(set(addrs) | set(stats)):
            stat = stats.get(name)
            ipv4 = _extract_ipv4(addrs.get(name, []))
            info = InterfaceInfo(
                name=name,
                is_up=bool(stat.isup) if stat is not None else False,
                is_loopback=_is_loopback(name, ipv4),
                speed_mbps=int(stat.speed) if stat is not None else 0,
                mtu=int(stat.mtu) if stat is not None else 0,
                ipv4_addresses=ipv4,
            )
            if include_all or (info.is_up and not info.is_loopback):
                result.append(info)
        return result

    def default_interface(self) -> str | None:
        """Chọn interface mặc định để giám sát.

        Tiêu chí: đang up, không phải loopback, có ít nhất một IPv4 hợp lệ không phải
        link-local (169.254.x.x) hoặc 0.0.0.0, và có bộ đếm; trong số đó chọn interface có
        tổng byte gửi + nhận lớn nhất. Đây chỉ là heuristic; có thể chỉ định interface thủ công.
        """
        counters = self._read_all_counters()
        best_name: str | None = None
        best_total = -1
        for info in self.list_interfaces():
            usable = [
                addr
                for addr in info.ipv4_addresses
                if not ipaddress.IPv4Address(addr).is_link_local
                and not ipaddress.IPv4Address(addr).is_unspecified
            ]
            current = counters.get(info.name)
            if not usable or current is None:
                continue
            total = current.sent_bytes + current.received_bytes
            if total > best_total:
                best_name, best_total = info.name, total
        return best_name

    def ensure_interface_up(self, interface: str) -> None:
        """Đảm bảo interface tồn tại và đang hoạt động trước khi lấy mẫu.

        ``net_io_counters(pernic=True)`` có thể vẫn trả về counters của adapter
        đã ngắt kết nối. Vì vậy không thể dùng sự tồn tại của counters để kết luận
        interface vẫn đang UP.
        """
        stat = self._if_stats().get(interface)
        if stat is None:
            raise InterfaceNotFoundError(f"Không tìm thấy trạng thái interface: {interface}")
        if not stat.isup:
            raise InterfaceDownError(f"Interface '{interface}' đang ngắt kết nối (DOWN)")

    def read_counters(self, interface: str) -> InterfaceCounters:
        """Đọc bộ đếm hiện tại của một interface."""
        counters = self._read_all_counters()
        if interface not in counters:
            raise InterfaceNotFoundError(f"Không tìm thấy interface: {interface}")
        return counters[interface]

    def sample(self, interface: str) -> TrafficSample:
        """Lấy một mẫu lưu lượng.

        Lần gọi đầu tiên cho một interface chỉ lưu mốc so sánh nên tốc độ là ``None``.
        Các lần sau, tốc độ là trung bình kể từ lần lấy mẫu trước của interface đó.
        """
        counters = self.read_counters(interface)
        now_monotonic = self._monotonic()
        timestamp = self._now()
        upload: float | None = None
        download: float | None = None
        with self._lock:
            baseline = self._baselines.get(interface)
            if baseline is not None:
                previous_time, previous = baseline
                elapsed = now_monotonic - previous_time
                if elapsed > 0:
                    upload = compute_rate(previous.sent_bytes, counters.sent_bytes, elapsed)
                    download = compute_rate(
                        previous.received_bytes, counters.received_bytes, elapsed
                    )
            self._baselines[interface] = (now_monotonic, counters)
        return TrafficSample(
            interface=interface,
            timestamp=timestamp,
            total_sent_bytes=counters.sent_bytes,
            total_received_bytes=counters.received_bytes,
            total_sent_packets=counters.sent_packets,
            total_received_packets=counters.received_packets,
            upload_bytes_per_second=upload,
            download_bytes_per_second=download,
        )

    def reset(self, interface: str | None = None) -> None:
        """Xóa mốc so sánh (của một interface hoặc tất cả), ví dụ khi đổi interface giám sát."""
        with self._lock:
            if interface is None:
                self._baselines.clear()
            else:
                self._baselines.pop(interface, None)

    def _read_all_counters(self) -> dict[str, InterfaceCounters]:
        return {
            name: InterfaceCounters(
                sent_bytes=int(raw.bytes_sent),
                received_bytes=int(raw.bytes_recv),
                sent_packets=int(raw.packets_sent),
                received_packets=int(raw.packets_recv),
            )
            for name, raw in self._io_counters().items()
        }
