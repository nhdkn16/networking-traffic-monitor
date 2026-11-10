"""Module TrafficAnalyzer: Phân tích phân bố giao thức và Top Talkers."""

from collections import Counter, defaultdict
from typing import Sequence

from network_monitor.models.schemas import AnalyticsSummary, PacketMetadata, ProtocolDistribution, TopTalkerItem


class TrafficAnalyzer:
    """Tổng hợp chỉ số thống kê từ danh sách PacketMetadata."""

    @staticmethod
    def analyze(packets: Sequence[PacketMetadata], top_n: int = 5) -> AnalyticsSummary:
        total_packets = len(packets)
        if total_packets == 0:
            return AnalyticsSummary(
                total_packets_analyzed=0,
                protocols=[],
                top_senders=[],
                top_receivers=[],
            )

        # 1. Thống kê phân bố giao thức
        proto_counts: Counter[str] = Counter()
        sender_bytes: dict[str, int] = defaultdict(int)
        sender_pkts: dict[str, int] = defaultdict(int)
        receiver_bytes: dict[str, int] = defaultdict(int)
        receiver_pkts: dict[str, int] = defaultdict(int)

        for pkt in packets:
            proto_counts[pkt.protocol] += 1

            if pkt.src_ip and pkt.src_ip != "0.0.0.0":
                sender_bytes[pkt.src_ip] += pkt.length_bytes
                sender_pkts[pkt.src_ip] += 1

            if pkt.dst_ip and pkt.dst_ip != "0.0.0.0":
                receiver_bytes[pkt.dst_ip] += pkt.length_bytes
                receiver_pkts[pkt.dst_ip] += 1

        protocols = [
            ProtocolDistribution(
                protocol=proto,
                packet_count=count,
                percentage=round((count / total_packets) * 100.0, 2),
            )
            for proto, count in proto_counts.most_common()
        ]

        # 2. Xếp hạng Top Senders
        sorted_senders = sorted(sender_bytes.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_senders = [
            TopTalkerItem(
                ip=ip,
                total_bytes=total_b,
                packet_count=sender_pkts[ip],
            )
            for ip, total_b in sorted_senders
        ]

        # 3. Xếp hạng Top Receivers
        sorted_receivers = sorted(receiver_bytes.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_receivers = [
            TopTalkerItem(
                ip=ip,
                total_bytes=total_b,
                packet_count=receiver_pkts[ip],
            )
            for ip, total_b in sorted_receivers
        ]

        return AnalyticsSummary(
            total_packets_analyzed=total_packets,
            protocols=protocols,
            top_senders=top_senders,
            top_receivers=top_receivers,
        )
        