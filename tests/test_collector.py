"""Kiểm thử NetworkCollector.

- Các test dùng dữ liệu psutil GIẢ chỉ nhằm kiểm tra logic (lọc interface, tính tốc độ,
  xử lý counter reset). Đây là mock phục vụ unit test, không phải số liệu của hệ thống thật.
- ``test_real_host_smoke`` đọc counters thật của máy đang chạy test.
"""

import socket
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from network_monitor.core.collector import (
    InterfaceNotFoundError,
    NetworkCollector,
    compute_rate,
)
from network_monitor.models.schemas import InterfaceInfo


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _io(sent: int, received: int, sent_packets: int = 0, received_packets: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        bytes_sent=sent,
        bytes_recv=received,
        packets_sent=sent_packets,
        packets_recv=received_packets,
    )


def _addr(ip: str, family: int = socket.AF_INET) -> SimpleNamespace:
    return SimpleNamespace(family=family, address=ip)


def _stat(isup: bool = True, speed: int = 0, mtu: int = 1500) -> SimpleNamespace:
    return SimpleNamespace(isup=isup, speed=speed, mtu=mtu)


def _fake_host() -> tuple[dict, dict, dict]:
    io = {
        "Loopback Pseudo-Interface 1": _io(999_999, 999_999),
        "Wi-Fi": _io(1_000, 5_000, 10, 50),
        "Ethernet": _io(0, 0),
        "Ethernet 2": _io(50_000, 50_000),
        "VirtualBox Host-Only": _io(10, 20),
    }
    addrs = {
        "Loopback Pseudo-Interface 1": [_addr("127.0.0.1")],
        "Wi-Fi": [_addr("192.168.2.7"), _addr("fe80::1", socket.AF_INET6)],
        "Ethernet": [],
        "Ethernet 2": [_addr("169.254.1.5")],
        "VirtualBox Host-Only": [_addr("192.168.56.1")],
    }
    stats = {
        "Loopback Pseudo-Interface 1": _stat(True, 1000),
        "Wi-Fi": _stat(True, 300),
        "Ethernet": _stat(False, 0),
        "Ethernet 2": _stat(True, 1000),
        "VirtualBox Host-Only": _stat(True, 1000),
    }
    return io, addrs, stats


def _make_collector(io: dict, addrs: dict, stats: dict, clock: FakeClock | None = None, now_func=None):
    return NetworkCollector(
        io_counters_func=lambda: io,
        if_addrs_func=lambda: addrs,
        if_stats_func=lambda: stats,
        monotonic_func=clock or FakeClock(),
        now_func=now_func,
    )


def test_compute_rate_basic() -> None:
    assert compute_rate(1_000, 3_000, 2.0) == 1_000.0


def test_compute_rate_counter_reset_returns_zero() -> None:
    assert compute_rate(5_000, 100, 1.0) == 0.0


@pytest.mark.parametrize("elapsed", [0, -1.0])
def test_compute_rate_invalid_elapsed_raises(elapsed: float) -> None:
    with pytest.raises(ValueError):
        compute_rate(0, 100, elapsed)


def test_list_interfaces_default_skips_loopback_and_down() -> None:
    collector = _make_collector(*_fake_host())
    names = [info.name for info in collector.list_interfaces()]
    assert names == ["Ethernet 2", "VirtualBox Host-Only", "Wi-Fi"]


def test_list_interfaces_include_all_and_fields() -> None:
    collector = _make_collector(*_fake_host())
    infos = {info.name: info for info in collector.list_interfaces(include_all=True)}
    assert len(infos) == 5
    assert all(isinstance(info, InterfaceInfo) for info in infos.values())
    wifi = infos["Wi-Fi"]
    assert wifi.is_up is True
    assert wifi.speed_mbps == 300
    assert wifi.ipv4_addresses == ["192.168.2.7"]  # IPv6 bị bỏ qua
    assert infos["Loopback Pseudo-Interface 1"].is_loopback is True
    assert infos["Ethernet"].is_up is False


def test_default_interface_prefers_usable_interface_with_most_traffic() -> None:
    collector = _make_collector(*_fake_host())
    # Loopback (nhiều byte nhất) và Ethernet 2 (chỉ có IP link-local) phải bị loại.
    assert collector.default_interface() == "Wi-Fi"


def test_default_interface_none_when_nothing_usable() -> None:
    io = {"Ethernet": _io(1, 1), "Ethernet 2": _io(2, 2)}
    addrs = {"Ethernet": [], "Ethernet 2": [_addr("169.254.1.5")]}
    stats = {"Ethernet": _stat(False), "Ethernet 2": _stat(True)}
    assert _make_collector(io, addrs, stats).default_interface() is None


def test_first_sample_has_no_rate() -> None:
    collector = _make_collector(*_fake_host())
    sample = collector.sample("Wi-Fi")
    assert sample.upload_bytes_per_second is None
    assert sample.download_bytes_per_second is None
    assert sample.total_sent_bytes == 1_000
    assert sample.total_received_bytes == 5_000
    assert sample.total_sent_packets == 10
    assert sample.total_received_packets == 50


def test_second_sample_computes_rate() -> None:
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    collector = _make_collector(io, addrs, stats, clock)
    collector.sample("Wi-Fi")
    io["Wi-Fi"] = _io(1_000 + 2_000, 5_000 + 10_000)
    clock.advance(2.0)
    sample = collector.sample("Wi-Fi")
    assert sample.upload_bytes_per_second == pytest.approx(1_000.0)
    assert sample.download_bytes_per_second == pytest.approx(5_000.0)


def test_counter_reset_between_samples_gives_zero_rate() -> None:
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    collector = _make_collector(io, addrs, stats, clock)
    collector.sample("Wi-Fi")
    io["Wi-Fi"] = _io(10, 20)
    clock.advance(1.0)
    sample = collector.sample("Wi-Fi")
    assert sample.upload_bytes_per_second == 0.0
    assert sample.download_bytes_per_second == 0.0


def test_unknown_interface_raises() -> None:
    collector = _make_collector(*_fake_host())
    with pytest.raises(InterfaceNotFoundError):
        collector.sample("Khong-Ton-Tai")


def test_baselines_are_independent_per_interface() -> None:
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    collector = _make_collector(io, addrs, stats, clock)
    collector.sample("Wi-Fi")
    clock.advance(1.0)
    other = collector.sample("VirtualBox Host-Only")
    assert other.upload_bytes_per_second is None


def test_reset_clears_baseline() -> None:
    io, addrs, stats = _fake_host()
    clock = FakeClock()
    collector = _make_collector(io, addrs, stats, clock)
    collector.sample("Wi-Fi")
    collector.reset("Wi-Fi")
    clock.advance(1.0)
    assert collector.sample("Wi-Fi").upload_bytes_per_second is None


def test_timestamp_comes_from_now_func_and_is_utc() -> None:
    fixed = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
    collector = _make_collector(*_fake_host(), now_func=lambda: fixed)
    sample = collector.sample("Wi-Fi")
    assert sample.timestamp == fixed
    assert sample.timestamp.utcoffset() == timedelta(0)


def test_real_host_smoke() -> None:
    psutil = pytest.importorskip("psutil")
    collector = NetworkCollector()
    interfaces = collector.list_interfaces(include_all=True)
    if not interfaces:
        pytest.skip("Máy này không có interface nào")
    real_counters = psutil.net_io_counters(pernic=True)
    if not real_counters:
        pytest.skip("psutil không trả về bộ đếm interface nào")
    name = collector.default_interface() or next(iter(real_counters))

    first = collector.sample(name)
    time.sleep(0.2)
    second = collector.sample(name)

    assert first.upload_bytes_per_second is None
    assert isinstance(second.upload_bytes_per_second, float)
    assert isinstance(second.download_bytes_per_second, float)
    assert second.upload_bytes_per_second >= 0
    assert second.download_bytes_per_second >= 0
    assert isinstance(second.total_sent_bytes, int) and second.total_sent_bytes >= 0
    assert isinstance(second.total_received_bytes, int) and second.total_received_bytes >= 0
    assert second.timestamp.tzinfo is not None
