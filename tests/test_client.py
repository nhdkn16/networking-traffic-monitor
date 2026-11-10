"""Kiểm thử tầng Client API và Reconnect/Resync."""

import asyncio
import numpy as np
from network_monitor.client.api_client import ApiClient
from network_monitor.client.connection_manager import ConnectionManager
from network_monitor.gui.client.main_window import format_bytes_speed, format_bytes_total


def test_api_client_init():
    async def _run():
        client = ApiClient("http://127.0.0.1:8000/")
        assert client.base_url == "http://127.0.0.1:8000"
        await client.close()

    asyncio.run(_run())


def test_connection_manager_init():
    cm = ConnectionManager("127.0.0.1", 8000)
    assert cm.api_url == "http://127.0.0.1:8000"
    assert cm.ws_url == "ws://127.0.0.1:8000/ws"


def test_format_helpers_with_nan():
    assert format_bytes_speed(np.nan) == "Chưa có dữ liệu"
    assert format_bytes_speed(None) == "Chưa có dữ liệu"
    assert format_bytes_speed(1500.0) == "1.50 KB/s"
    assert format_bytes_total(1000000) == "1.00 MB"
    