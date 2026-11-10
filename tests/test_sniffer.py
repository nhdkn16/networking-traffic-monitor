"""Kiểm thử đơn vị module PacketSniffer."""

import time
from network_monitor.core.sniffer import PacketSniffer
from network_monitor.models.schemas import PacketMetadata

def test_sniffer_initial_state():
    sniffer = PacketSniffer()
    status = sniffer.get_status()
    assert status.is_running is False
    assert status.packet_count == 0
    assert len(sniffer.get_recent_packets()) == 0

def test_sniffer_start_stop_mock():
    sniffer = PacketSniffer()
    # Bắt đầu trên interface giả lập (sẽ tạo thread)
    assert sniffer.start("Wi-Fi") is True
    status = sniffer.get_status()
    assert status.interface == "Wi-Fi"

    sniffer.stop()
    status_after = sniffer.get_status()
    assert status_after.is_running is False

def test_sniffer_ring_buffer_limit():
    sniffer = PacketSniffer(max_buffer_size=5)
    # Giả lập nạp 10 gói tin vào bộ nhớ
    import datetime
    for i in range(10):
        meta = PacketMetadata(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            src_ip=f"192.168.1.{i}",
            dst_ip="10.0.0.1",
            protocol="TCP",
            length_bytes=64
        )
        sniffer._packets.append(meta)

    packets = sniffer.get_recent_packets(limit=10)
    assert len(packets) == 5  # Ring buffer chỉ giữ 5 gói tin gần nhất
    assert packets[-1].src_ip == "192.168.1.9"
    