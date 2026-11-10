"""Module ProcessMapper: Ánh xạ IP/Port sang Tên Tiến trình (.exe) và PID."""

import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ProcessMapper:
    """Quản lý tra cứu và cache ánh xạ (Giao thức, IP, Port) -> Tiến trình (.exe)."""

    def __init__(self, cache_ttl: float = 1.0) -> None:
        self.cache_ttl = cache_ttl
        self._last_refresh = 0.0
        self._port_map: Dict[Tuple[str, int], Tuple[str, Optional[int]]] = {}
        self._ip_port_map: Dict[Tuple[str, int], Tuple[str, Optional[int]]] = {}
        self._pid_name_cache: Dict[int, str] = {}

    def _refresh_cache_if_needed(self) -> None:
        """Cập nhật bảng socket mạng từ OS bằng psutil nếu hết hạn TTL."""
        now = time.time()
        if now - self._last_refresh < self.cache_ttl:
            return
        self._last_refresh = now

        try:
            import psutil

            new_port_map: Dict[Tuple[str, int], Tuple[str, Optional[int]]] = {}
            new_ip_port_map: Dict[Tuple[str, int], Tuple[str, Optional[int]]] = {}

            # Lấy danh sách kết nối mạng IPv4/IPv6 hiện tại
            connections = psutil.net_connections(kind="inet")
            for conn in connections:
                pid = conn.pid
                if not pid:
                    continue

                if pid not in self._pid_name_cache:
                    try:
                        proc = psutil.Process(pid)
                        self._pid_name_cache[pid] = proc.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        self._pid_name_cache[pid] = f"PID:{pid}"
                    except Exception:
                        self._pid_name_cache[pid] = "System"

                proc_name = self._pid_name_cache.get(pid, "System")
                proto = "TCP" if conn.type == 1 else "UDP"

                if conn.laddr:
                    new_port_map[(proto, conn.laddr.port)] = (proc_name, pid)
                    new_ip_port_map[(conn.laddr.ip, conn.laddr.port)] = (proc_name, pid)
                if conn.raddr:
                    new_ip_port_map[(conn.raddr.ip, conn.raddr.port)] = (proc_name, pid)

            self._port_map = new_port_map
            self._ip_port_map = new_ip_port_map

        except Exception as e:
            logger.debug("Không thể đọc danh sách net_connections từ psutil: %s", e)

    def get_process_info(
        self,
        protocol: str,
        src_ip: str,
        src_port: Optional[int],
        dst_ip: str,
        dst_port: Optional[int],
    ) -> Tuple[str, Optional[int]]:
        """Tra cứu tên tiến trình (.exe) và PID dựa trên địa chỉ IP và Port."""
        self._refresh_cache_if_needed()
        proto = (protocol or "").upper()

        # 1. Kiểm tra theo Cổng / IP Nguồn
        if src_port:
            if (proto, src_port) in self._port_map:
                return self._port_map[(proto, src_port)]
            if (src_ip, src_port) in self._ip_port_map:
                return self._ip_port_map[(src_ip, src_port)]

        # 2. Kiểm tra theo Cổng / IP Đích
        if dst_port:
            if (proto, dst_port) in self._port_map:
                return self._port_map[(proto, dst_port)]
            if (dst_ip, dst_port) in self._ip_port_map:
                return self._ip_port_map[(dst_ip, dst_port)]

        return ("Unknown / System", None)
    