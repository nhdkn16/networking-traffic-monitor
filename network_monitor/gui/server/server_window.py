import sys
import dataclasses
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QPushButton, QLineEdit,
    QSpinBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from network_monitor.config import Settings
from network_monitor.gui.server.server_thread import ServerWorkerThread

class ServerMainWindow(QMainWindow):
    """Cửa sổ quản trị Server GUI (PyQt6 trên Host)."""

    def __init__(self, default_settings: Settings | None = None):
        super().__init__()
        self.settings = default_settings or Settings()
        self.worker_thread: ServerWorkerThread | None = None

        self.setWindowTitle("Network Monitor - Server Management Console (Host)")
        self.resize(900, 600)

        self._init_ui()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Thanh cấu hình Server
        cfg_box = QGroupBox("Cấu hình và Điều khiển Server")
        cfg_layout = QHBoxLayout(cfg_box)

        cfg_layout.addWidget(QLabel("Host:"))
        self.host_input = QLineEdit(self.settings.host)
        cfg_layout.addWidget(self.host_input)

        cfg_layout.addWidget(QLabel("Cổng:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(self.settings.port)
        cfg_layout.addWidget(self.port_input)

        cfg_layout.addWidget(QLabel("Interface:"))
        self.iface_input = QLineEdit(self.settings.interface or "")
        self.iface_input.setPlaceholderText("Tự động chọn (Auto)")
        cfg_layout.addWidget(self.iface_input)

        self.btn_toggle = QPushButton("Khởi động Server")
        self.btn_toggle.setStyleSheet("font-weight: bold; background-color: #5cb85c; color: white; padding: 5px 15px;")
        self.btn_toggle.clicked.connect(self._toggle_server)
        cfg_layout.addWidget(self.btn_toggle)

        main_layout.addWidget(cfg_box)

        # 2. Trạng thái hoạt động
        status_box = QGroupBox("Trạng thái dịch vụ Server")
        status_layout = QGridLayout(status_box)

        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(10)

        status_layout.addWidget(QLabel("Trạng thái Server:"), 0, 0)
        self.lbl_server_status = QLabel("Đang dừng")
        self.lbl_server_status.setFont(bold_font)
        self.lbl_server_status.setStyleSheet("color: red;")
        status_layout.addWidget(self.lbl_server_status, 0, 1)

        status_layout.addWidget(QLabel("URL HTTP REST / WS:"), 0, 2)
        self.lbl_url = QLabel(f"http://{self.settings.host}:{self.settings.port}")
        self.lbl_url.setFont(bold_font)
        status_layout.addWidget(self.lbl_url, 0, 3)

        status_layout.addWidget(QLabel("Interface thu thập:"), 1, 0)
        self.lbl_interface = QLabel(self.settings.interface or "Auto")
        self.lbl_interface.setFont(bold_font)
        status_layout.addWidget(self.lbl_interface, 1, 1)

        status_layout.addWidget(QLabel("Tài liệu API:"), 1, 2)
        self.lbl_docs = QLabel(f"http://{self.settings.host}:{self.settings.port}/docs")
        self.lbl_docs.setFont(bold_font)
        status_layout.addWidget(self.lbl_docs, 1, 3)

        main_layout.addWidget(status_box)

        # 3. Nhật ký Server (Console log)
        log_box = QGroupBox("Nhật ký dịch vụ (Server Logs)")
        log_layout = QVBoxLayout(log_box)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        main_layout.addWidget(log_box, stretch=1)

    def _toggle_server(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self) -> None:
        host = self.host_input.text().strip() or "127.0.0.1"
        port = self.port_input.value()
        iface = self.iface_input.text().strip() or None

        current_settings = dataclasses.replace(
            self.settings,
            host=host,
            port=port,
            interface=iface
        )

        self.lbl_url.setText(f"http://{host}:{port}")
        self.lbl_docs.setText(f"http://{host}:{port}/docs")
        self.lbl_interface.setText(iface or "Auto")

        self.btn_toggle.setText("Đang khởi động...")
        self.btn_toggle.setEnabled(False)

        self.worker_thread = ServerWorkerThread(current_settings)
        self.worker_thread.log_signal.connect(self._on_log)
        self.worker_thread.status_signal.connect(self._on_status)
        self.worker_thread.start()

    def _stop_server(self) -> None:
        if self.worker_thread:
            self.log_text.append("[HỆ THỐNG] Đang yêu cầu dừng Server...")
            self.btn_toggle.setText("Đang dừng...")
            self.btn_toggle.setEnabled(False)
            self.worker_thread.stop()
            self.worker_thread.wait(3000)
            self.worker_thread = None

        self._on_status("stopped", "Server đã dừng.")

    @pyqtSlot(str, str)
    def _on_status(self, code: str, msg: str) -> None:
        if code == "running":
            self.lbl_server_status.setText("Đang hoạt động")
            self.lbl_server_status.setStyleSheet("color: green; font-weight: bold;")
            self.btn_toggle.setText("Dừng Server")
            self.btn_toggle.setStyleSheet("font-weight: bold; background-color: #d9534f; color: white; padding: 5px 15px;")
            self.btn_toggle.setEnabled(True)
            self.host_input.setEnabled(False)
            self.port_input.setEnabled(False)
            self.iface_input.setEnabled(False)
        elif code == "stopped":
            self.lbl_server_status.setText("Đang dừng")
            self.lbl_server_status.setStyleSheet("color: red; font-weight: bold;")
            self.btn_toggle.setText("Khởi động Server")
            self.btn_toggle.setStyleSheet("font-weight: bold; background-color: #5cb85c; color: white; padding: 5px 15px;")
            self.btn_toggle.setEnabled(True)
            self.host_input.setEnabled(True)
            self.port_input.setEnabled(True)
            self.iface_input.setEnabled(True)
        self.log_text.append(f"[TRẠNG THÁI] {msg}")

    @pyqtSlot(str)
    def _on_log(self, msg: str) -> None:
        self.log_text.append(msg)

    def closeEvent(self, event) -> None:
        self._stop_server()
        event.accept()

def run_server_gui(settings: Settings | None = None) -> None:
    app = QApplication(sys.argv)
    window = ServerMainWindow(default_settings=settings)
    window.show()
    sys.exit(app.exec())
    