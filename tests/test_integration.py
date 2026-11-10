"""Kiểm thử tích hợp End-to-End (E2E) toàn bộ hệ thống Network Monitor."""

import asyncio
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from network_monitor.config import Settings
from network_monitor.models.schemas import AlertRule, PacketMetadata
from network_monitor.server.main import create_app
from network_monitor.server.monitoring_service import MonitoringService
from tests.test_collector import FakeClock, _fake_host, _io, _make_collector


@pytest.fixture
def integration_app():
    """Tạo FastAPI application với mock collector phục vụ kiểm thử tích hợp."""
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    collector = _make_collector(io, addrs, stats, clock)
    settings = Settings(host="127.0.0.1", port=8000, sample_interval_seconds=0.1)

    app = create_app(settings)
    service = MonitoringService(collector, settings)
    app.state.service = service
    app.state.monitoring_service = service
    return app, service, io, clock


def test_full_e2e_lifecycle(integration_app):
    app, service, io, clock = integration_app

    with TestClient(app) as client:
        # 1. Kiểm tra HTTP REST Health & Interfaces
        res_health = client.get("/api/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

        res_ifaces = client.get("/api/interfaces")
        assert res_ifaces.status_code == 200
        assert len(res_ifaces.json()["interfaces"]) > 0

        # 2. Giả lập vòng lấy mẫu sinh dữ liệu tốc độ (Cộng dồn vào mốc ban đầu 1,000 / 5,000)
        asyncio.run(service.sample_once())
        io["Wi-Fi"] = _io(1_000 + 10_000, 5_000 + 50_000)
        clock.advance(1.0)
        asyncio.run(service.sample_once())

        # 3. Truy vấn mẫu thống kê lưu lượng hiện tại
        res_stat = client.get("/api/statistics/current")
        assert res_stat.status_code == 200
        data_stat = res_stat.json()
        assert data_stat["upload_bytes_per_second"] == pytest.approx(10_000.0)
        assert data_stat["download_bytes_per_second"] == pytest.approx(50_000.0)

        # 4. Bắt đầu Packet Capture & Nạp gói tin giả lập
        res_cap_start = client.post("/api/capture/start?interface=Wi-Fi")
        assert res_cap_start.status_code == 200
        assert res_cap_start.json()["is_running"] is True

        # Nạp trực tiếp 5 gói tin vào sniffer buffer để kiểm tra phân tích
        for i in range(5):
            service._sniffer._packets.append(
                PacketMetadata(
                    timestamp=datetime.now(timezone.utc),
                    src_ip=f"192.168.1.{10+i}",
                    dst_ip="8.8.8.8",
                    protocol="TCP" if i % 2 == 0 else "UDP",
                    length_bytes=1000 * (i + 1),
                )
            )

        res_packets = client.get("/api/capture/packets?limit=10")
        assert res_packets.status_code == 200
        assert len(res_packets.json()) == 5

        # 5. Kiểm tra Analytics Summary & Top Talkers
        res_analytics = client.get("/api/analytics/summary?top_n=5")
        assert res_analytics.status_code == 200
        analytics = res_analytics.json()
        assert analytics["total_packets_analyzed"] == 5
        assert len(analytics["protocols"]) == 2
        assert len(analytics["top_senders"]) == 5

        # 6. Thiết lập quy tắc Alert và kích hoạt cảnh báo
        rule = AlertRule(max_upload_bytes_per_sec=5000.0, enabled=True)
        res_alert_cfg = client.post("/api/alerts/config", json=rule.model_dump())
        assert res_alert_cfg.status_code == 200

        # Kích hoạt mẫu vượt ngưỡng upload (10,000 > 5,000)
        io["Wi-Fi"] = _io(1_000 + 20_000, 5_000 + 60_000)
        clock.advance(1.0)
        asyncio.run(service.sample_once())

        res_alerts = client.get("/api/alerts/history")
        assert res_alerts.status_code == 200
        history = res_alerts.json()
        assert len(history) >= 1
        assert history[-1]["alert_type"] == "upload_exceeded"

        # 7. Dừng Packet Capture
        res_cap_stop = client.post("/api/capture/stop")
        assert res_cap_stop.status_code == 200
        assert res_cap_stop.json()["is_running"] is False
        