"""Kiểm thử HTTP API bằng TestClient.

Collector giả (mock) chỉ phục vụ kiểm tra logic API; không phải số liệu của hệ thống thật.
"""
# Các helper dưới đây được dùng lại từ test_collector để tránh trùng lặp.
import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from network_monitor import __version__
from network_monitor.config import Settings
from network_monitor.server.main import create_app
from network_monitor.server.monitoring_service import MonitoringService
from tests.test_collector import FakeClock, _addr, _fake_host, _io, _make_collector, _stat


def _primed_service() -> MonitoringService:
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    service = MonitoringService(_make_collector(io, addrs, stats, clock), Settings())
    asyncio.run(service.sample_once())  # mốc
    io["Wi-Fi"] = _io(1_000 + 2_000, 5_000 + 10_000)
    clock.advance(2.0)
    asyncio.run(service.sample_once())  # tốc độ: gửi 1000 B/s, nhận 5000 B/s
    return service


def _service_without_usable_interface() -> MonitoringService:
    io = {"Ethernet": _io(1, 1), "Ethernet 2": _io(2, 2)}
    addrs = {"Ethernet": [], "Ethernet 2": [_addr("169.254.1.5")]}
    stats = {"Ethernet": _stat(False), "Ethernet 2": _stat(True)}
    return MonitoringService(_make_collector(io, addrs, stats), Settings())


def test_health_ok() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["monitored_interface"] == "Wi-Fi"
    assert body["last_error"] is None
    assert body["uptime_seconds"] >= 0
    assert body["websocket_clients"] == 0
    datetime.fromisoformat(body["server_time"])


def test_health_degraded_when_no_usable_interface() -> None:
    service = _service_without_usable_interface()
    asyncio.run(service.sample_once())
    client = TestClient(create_app(service=service, autostart=False))
    response = client.get("/api/health")
    assert response.status_code == 200  # HTTP Server vẫn chạy
    body = response.json()
    assert body["status"] == "degraded"
    assert body["last_error"]


def test_interfaces_default_and_include_all() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    body = client.get("/api/interfaces").json()
    assert body["monitored_interface"] == "Wi-Fi"
    assert [i["name"] for i in body["interfaces"]] == [
        "Ethernet 2",
        "VirtualBox Host-Only",
        "Wi-Fi",
    ]
    wifi = next(i for i in body["interfaces"] if i["name"] == "Wi-Fi")
    assert wifi["ipv4_addresses"] == ["192.168.2.7"]
    assert wifi["speed_mbps"] == 300

    all_body = client.get("/api/interfaces", params={"include_all": "true"}).json()
    assert len(all_body["interfaces"]) == 5


def test_statistics_current_returns_latest_sample() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    response = client.get("/api/statistics/current")
    assert response.status_code == 200
    body = response.json()
    assert body["interface"] == "Wi-Fi"
    assert body["upload_bytes_per_second"] == pytest.approx(1_000.0)
    assert body["download_bytes_per_second"] == pytest.approx(5_000.0)
    assert body["total_sent_bytes"] == 3_000
    assert body["total_received_bytes"] == 15_000
    datetime.fromisoformat(body["timestamp"])


def test_statistics_503_before_first_rate() -> None:
    io, addrs, stats = _fake_host()
    service = MonitoringService(_make_collector(io, addrs, stats), Settings())
    client = TestClient(create_app(service=service, autostart=False))
    response = client.get("/api/statistics/current")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert "Chưa có dữ liệu" in response.json()["detail"]


def test_statistics_503_with_reason_when_no_interface() -> None:
    service = _service_without_usable_interface()
    asyncio.run(service.sample_once())
    client = TestClient(create_app(service=service, autostart=False))
    response = client.get("/api/statistics/current")
    assert response.status_code == 503
    assert "interface" in response.json()["detail"]


def test_openapi_lists_endpoints() -> None:
    client = TestClient(create_app(service=_primed_service(), autostart=False))
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/health", "/api/interfaces", "/api/statistics/current"):
        assert path in paths


def test_lifespan_starts_and_stops_sampler() -> None:
    io, addrs, stats = _fake_host()
    service = MonitoringService(
        _make_collector(io, addrs, stats), Settings(sample_interval_seconds=0.01)
    )
    app = create_app(service=service, autostart=True)
    with TestClient(app) as client:
        assert service.is_running
        assert client.get("/api/health").status_code == 200
    assert not service.is_running
