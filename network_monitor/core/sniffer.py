"""Module PacketSniffer: Bắt và phân tích metadata gói tin bằng Scapy."""

import collections
import datetime
import logging
import threading
from typing import Optional

from network_monitor.models.schemas import CaptureStatus, PacketMetadata

logger = logging.getLogger(__name__)


class PacketSniffer:
    """Quản lý tiến trình bắt và phân tích metadata gói tin sử dụng Scapy."""

    def __init__(self, max_buffer_size: int = 1000) -> None:
        self.max_buffer_size = max_buffer_size
        self._packets: collections.deque[PacketMetadata] = collections.deque(maxlen=max_buffer_size)
        self._is_running = False
        self._interface: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._error_message: Optional[str] = None
        self._packet_count = 0
        self._lock = threading.Lock()

    def get_status(self) -> CaptureStatus:
        with self._lock:
            return CaptureStatus(
                is_running=self._is_running,
                interface=self._interface,
                packet_count=self._packet_count,
                error_message=self._error_message,
            )

    def get_recent_packets(self, limit: int = 100) -> list[PacketMetadata]:
        with self._lock:
            packets = list(self._packets)
            return packets[-limit:]

    def start(self, interface: str) -> bool:
        with self._lock:
            if self._is_running:
                return True
            self._interface = interface
            self._error_message = None
            self._is_running = True
            self._packets.clear()
            self._packet_count = 0

        self._thread = threading.Thread(
            target=self._sniff_loop,
            args=(interface,),
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _sniff_loop(self, interface: str) -> None:
        try:
            from scapy.all import IP, IPv6, TCP, UDP, ICMP, sniff
        except ImportError as e:
            with self._lock:
                self._is_running = False
                self._error_message = f"Thiếu thư viện Scapy hoặc driver Npcap: {e}"
            return

        def process_packet(pkt) -> None:
            if not self._running_check():
                return

            try:
                src_ip = "0.0.0.0"
                dst_ip = "0.0.0.0"
                protocol = "OTHER"
                src_port = None
                dst_port = None

                if pkt.haslayer(IP):
                    src_ip = pkt[IP].src
                    dst_ip = pkt[IP].dst
                    protocol = "IPv4"
                elif pkt.haslayer(IPv6):
                    src_ip = pkt[IPv6].src
                    dst_ip = pkt[IPv6].dst
                    protocol = "IPv6"

                if pkt.haslayer(TCP):
                    protocol = "TCP"
                    src_port = int(pkt[TCP].sport)
                    dst_port = int(pkt[TCP].dport)
                elif pkt.haslayer(UDP):
                    protocol = "UDP"
                    src_port = int(pkt[UDP].sport)
                    dst_port = int(pkt[UDP].dport)
                elif pkt.haslayer(ICMP):
                    protocol = "ICMP"

                metadata = PacketMetadata(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    src_ip=src_ip,
                    dst_ip=dst_ip,
                    src_port=src_port,
                    dst_port=dst_port,
                    protocol=protocol,
                    length_bytes=len(pkt),
                )

                with self._lock:
                    self._packets.append(metadata)
                    self._packet_count += 1

            except Exception as exc:
                logger.debug(f"Lỗi khi xử lý gói tin Scapy: {exc}")

        try:
            sniff(
                iface=interface,
                prn=process_packet,
                store=False,
                stop_filter=lambda p: not self._running_check(),
            )
        except Exception as exc:
            with self._lock:
                self._is_running = False
                self._error_message = f"Lỗi Scapy/Npcap (Cần quyền Administrator): {exc}"
                logger.error(f"Lỗi bắt gói tin trên {interface}: {exc}")

    def _running_check(self) -> bool:
        with self._lock:
            return self._is_running

    def add_packet_metadata(self, metadata: PacketMetadata) -> None:
        """Nạp trực tiếp một đối tượng PacketMetadata vào Ring Buffer và tăng đếm gói tin."""
        if hasattr(self, "_packets"):
            self._packets.append(metadata)
        elif hasattr(self, "packets"):
            self.packets.append(metadata)

        if hasattr(self, "_packet_count"):
            self._packet_count += 1
        elif hasattr(self, "packet_count"):
            self.packet_count += 1
            