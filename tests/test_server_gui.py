"""Kiểm thử khởi tạo Server GUI."""

import pytest
from PyQt6.QtWidgets import QApplication
from network_monitor.config import Settings
from network_monitor.gui.server.server_window import ServerMainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_server_window_init(qapp):
    settings = Settings(host="127.0.0.1", port=8000)
    window = ServerMainWindow(default_settings=settings)
    assert window.host_input.text() == "127.0.0.1"
    assert window.port_input.value() == 8000
    assert window.lbl_server_status.text() == "Đang dừng"
    