"""Kiểm thử MonitoringService.

Collector giả (mock) chỉ phục vụ kiểm tra logic; không phải số liệu của hệ thống thật.
"""
# Các helper dưới đây được dùng lại từ test_collector để tránh trùng lặp.
import asyncio

import pytest

from network_monitor.config import Settings
from network_monitor.server.monitoring_service import MonitoringService
from tests.test_collector import FakeClock, _addr, _fake_host, _io, _make_collector, _stat


def _service(settings: Settings | None = None):
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    service = MonitoringService(_make_collector(io, addrs, stats, clock), settings or Settings())
    return service, io, addrs, stats, clock


def _prime(service: MonitoringService, io: dict, clock: FakeClock) -> None:
    """Lấy mẫu hai lần: lần 1 là mốc, lần 2 cho tốc độ 1000 B/s gửi và 5000 B/s nhận."""
    asyncio.run(service.sample_once())
    io["Wi-Fi"] = _io(1_000 + 2_000, 5_000 + 10_000)
    clock.advance(2.0)
    asyncio.run(service.sample_once())


def test_no_published_sample_before_second_sample() -> None:
    service, *_ = _service()
    asyncio.run(service.sample_once())
    assert service.interface == "Wi-Fi"
    assert service.latest_sample() is None  # mới có mốc, không công bố số 0 giả
    assert service.last_error is None


def test_publishes_rates_after_second_sample() -> None:
    service, io, _addrs, _stats, clock = _service()
    _prime(service, io, clock)
    sample = service.latest_sample()
    assert sample is not None
    assert sample.interface == "Wi-Fi"
    assert sample.upload_bytes_per_second == pytest.approx(1_000.0)
    assert sample.download_bytes_per_second == pytest.approx(5_000.0)


def test_no_usable_interface_sets_error() -> None:
    io = {"Ethernet": _io(1, 1), "Ethernet 2": _io(2, 2)}
    addrs = {"Ethernet": [], "Ethernet 2": [_addr("169.254.1.5")]}
    stats = {"Ethernet": _stat(False), "Ethernet 2": _stat(True)}
    service = MonitoringService(_make_collector(io, addrs, stats), Settings())
    asyncio.run(service.sample_once())
    assert service.latest_sample() is None
    assert service.last_error is not None


def test_pinned_unknown_interface_sets_error_and_keeps_name() -> None:
    service, *_ = _service(Settings(interface="Khong-Ton-Tai"))
    asyncio.run(service.sample_once())
    assert service.latest_sample() is None
    assert "Khong-Ton-Tai" in service.last_error
    assert service.interface == "Khong-Ton-Tai"


def test_pinned_interface_drops_stale_data_then_recovers() -> None:
    service, io, _addrs, _stats, clock = _service(Settings(interface="Wi-Fi"))
    _prime(service, io, clock)
    assert service.latest_sample() is not None

    saved = io.pop("Wi-Fi")  # interface biến mất
    clock.advance(1.0)
    asyncio.run(service.sample_once())
    assert service.latest_sample() is None  # không giữ dữ liệu cũ
    assert service.last_error is not None

    io["Wi-Fi"] = saved  # interface quay lại
    clock.advance(1.0)
    asyncio.run(service.sample_once())  # mốc mới
    assert service.latest_sample() is None
    io["Wi-Fi"] = _io(saved.bytes_sent + 500, saved.bytes_recv + 1_000)
    clock.advance(1.0)
    asyncio.run(service.sample_once())
    sample = service.latest_sample()
    assert sample is not None
    assert sample.upload_bytes_per_second == pytest.approx(500.0)
    assert service.last_error is None


def test_auto_mode_reselects_interface_after_it_disappears() -> None:
    service, io, _addrs, _stats, clock = _service()
    asyncio.run(service.sample_once())
    assert service.interface == "Wi-Fi"
    io.pop("Wi-Fi")
    clock.advance(1.0)
    asyncio.run(service.sample_once())  # lỗi: interface cũ biến mất
    assert service.interface is None
    asyncio.run(service.sample_once())  # chọn lại interface mặc định còn dùng được
    assert service.interface == "VirtualBox Host-Only"


def test_start_stop_lifecycle() -> None:
    async def scenario() -> None:
        service, *_ = _service(Settings(sample_interval_seconds=0.01))
        assert not service.is_running
        await service.start()
        await service.start()  # gọi lại không tạo thêm tác vụ
        assert service.is_running
        await asyncio.sleep(0.05)
        await service.stop()
        assert not service.is_running
        await service.stop()  # idempotent

    asyncio.run(scenario())


def test_status_data_reflects_state() -> None:
    service, *_ = _service()
    assert service.status_data().status == "ok"
    assert service.status_data().sample_interval_seconds == 1.0
    asyncio.run(service.sample_once())
    assert service.status_data().monitored_interface == "Wi-Fi"

    io = {"Ethernet": _io(1, 1)}
    addrs = {"Ethernet": []}
    stats = {"Ethernet": _stat(False)}
    broken = MonitoringService(_make_collector(io, addrs, stats), Settings())
    asyncio.run(broken.sample_once())
    status = broken.status_data()
    assert status.status == "degraded"
    assert status.last_error


def test_sample_listener_called_only_for_published_samples() -> None:
    service, io, _addrs, _stats, clock = _service()
    received = []

    async def listener(sample) -> None:
        received.append(sample)

    service.add_sample_listener(listener)
    asyncio.run(service.sample_once())  # mốc: chưa công bố
    assert received == []
    io["Wi-Fi"] = _io(1_000 + 2_000, 5_000 + 10_000)
    clock.advance(2.0)
    asyncio.run(service.sample_once())
    assert len(received) == 1
    assert received[0].upload_bytes_per_second == pytest.approx(1_000.0)


def test_status_listener_called_on_change_only() -> None:
    service, io, _addrs, _stats, clock = _service(Settings(interface="Wi-Fi"))
    calls: list[str] = []

    async def listener() -> None:
        calls.append(service.status_data().status)

    service.add_status_listener(listener)
    asyncio.run(service.sample_once())
    assert calls == []  # không đổi trạng thái thì không thông báo

    saved = io.pop("Wi-Fi")
    clock.advance(1.0)
    asyncio.run(service.sample_once())
    asyncio.run(service.sample_once())  # cùng lỗi lặp lại: không thông báo thêm
    assert calls == ["degraded"]

    io["Wi-Fi"] = saved
    clock.advance(1.0)
    asyncio.run(service.sample_once())
    assert calls == ["degraded", "ok"]


def test_failing_listener_does_not_break_sampling() -> None:
    service, io, _addrs, _stats, clock = _service()
    delivered = []

    async def bad(sample) -> None:
        raise RuntimeError("listener lỗi")

    async def good(sample) -> None:
        delivered.append(sample)

    service.add_sample_listener(bad)
    service.add_sample_listener(good)
    _prime(service, io, clock)
    assert service.latest_sample() is not None
    assert len(delivered) == 1
