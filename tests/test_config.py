"""Kiểm thử cấu hình tập trung."""

import pytest

from network_monitor.config import (
    ENV_HOST,
    ENV_INTERFACE,
    ENV_INTERVAL,
    ENV_MAX_WS_CLIENTS,
    ENV_PORT,
    Settings,
)


def test_defaults() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.sample_interval_seconds == 1.0
    assert settings.interface is None
    assert settings.max_ws_clients == 20


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_invalid_port_raises(port: int) -> None:
    with pytest.raises(ValueError):
        Settings(port=port)


def test_invalid_interval_raises() -> None:
    with pytest.raises(ValueError):
        Settings(sample_interval_seconds=0)


def test_invalid_max_ws_clients_raises() -> None:
    with pytest.raises(ValueError):
        Settings(max_ws_clients=0)


def test_empty_host_or_interface_raises() -> None:
    with pytest.raises(ValueError):
        Settings(host="  ")
    with pytest.raises(ValueError):
        Settings(interface="")


def test_from_env_empty_uses_defaults() -> None:
    assert Settings.from_env({}) == Settings()


def test_from_env_overrides() -> None:
    settings = Settings.from_env(
        {
            ENV_HOST: "0.0.0.0",
            ENV_PORT: "9000",
            ENV_INTERVAL: "0.5",
            ENV_INTERFACE: "Wi-Fi",
            ENV_MAX_WS_CLIENTS: "5",
        }
    )
    assert settings == Settings(
        host="0.0.0.0", port=9000, sample_interval_seconds=0.5, interface="Wi-Fi", max_ws_clients=5
    )


def test_from_env_invalid_number_raises() -> None:
    with pytest.raises(ValueError):
        Settings.from_env({ENV_PORT: "abc"})
    with pytest.raises(ValueError):
        Settings.from_env({ENV_INTERVAL: "abc"})
    with pytest.raises(ValueError):
        Settings.from_env({ENV_MAX_WS_CLIENTS: "abc"})
