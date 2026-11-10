"""Màn hình chính giao diện Client GUI (PyQt6 & pyqtgraph)."""

import sys
from typing import Any, Dict, List
import numpy as np
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph as pg

from network_monitor.gui.client.worker import ClientWorker


def format_bytes_speed(bytes_per_sec: float | None) -> str:
    if bytes_per_sec is None or (isinstance(bytes_per_sec, float) and np.isnan(bytes_per_sec)):
        return "Chưa có dữ liệu"
    if bytes_per_sec >= 1_000_000:
        return f"{bytes_per_sec / 1_000_000:.2f} MB/s"
    return f"{bytes_per_sec / 1000:.2f} KB/s"


def format_bytes_total(total_bytes: int | None) -> str:
    if total_bytes is None:
        return "Chưa có dữ liệu"
    if total_bytes >= 1_000_000_000:
        return f"{total_bytes / 1_000_000_000:.2f} GB"
    if total_bytes >= 1_000_000:
        return f"{total_bytes / 1_000_000:.2f} MB"
    return f"{total_bytes / 1000:.2f} KB"


class MainWindow(QMainWindow):
    def __init__(self, default_host: str = "127.0.0.1", default_port: int = 8000):
        super().__init__()
        self.setWindowTitle("Network Monitor - Client GUI (Giám sát Băng thông, Sniffer & Traffic Alerts)")
        self.resize(1080, 780)

        self.worker: ClientWorker | None = None
        self.history_limit = 60
        self.upload_history: List[float] = []
        self.download_history: List[float] = []
        self.captured_packets_data: List[Dict[str, Any]] = []

        self._init_ui(default_host, default_port)

    def _init_ui(self, default_host: str, default_port: int) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Thanh điều khiển kết nối chung
        conn_box = QGroupBox("Cấu hình kết nối Server")
        conn_layout = QHBoxLayout(conn_box)

        conn_layout.addWidget(QLabel("Địa chỉ Server IP:"))
        self.host_input = QLineEdit(default_host)
        conn_layout.addWidget(self.host_input)

        conn_layout.addWidget(QLabel("Cổng:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(default_port)
        conn_layout.addWidget(self.port_input)

        self.btn_connect = QPushButton("Kết nối")
        self.btn_connect.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self.btn_connect)

        self.lbl_status = QLabel("Trạng thái: Chưa kết nối")
        self.lbl_status.setStyleSheet("font-weight: bold; color: gray;")
        conn_layout.addWidget(self.lbl_status)

        main_layout.addWidget(conn_box)

        # 2. Thẻ Tab
        self.tabs = QTabWidget()

        self.tab_traffic = QWidget()
        self._init_traffic_tab(self.tab_traffic)
        self.tabs.addTab(self.tab_traffic, "Giám sát Lưu lượng Realtime")

        self.tab_capture = QWidget()
        self._init_capture_tab(self.tab_capture)
        self.tabs.addTab(self.tab_capture, "Bắt gói tin & Deep Inspection")

        self.tab_analytics = QWidget()
        self._init_analytics_tab(self.tab_analytics)
        self.tabs.addTab(self.tab_analytics, "Phân tích Giao thức & Top Talkers")

        self.tab_alerts = QWidget()
        self._init_alerts_tab(self.tab_alerts)
        self.tabs.addTab(self.tab_alerts, "Cảnh báo Lưu lượng & Lịch sử Alert")

        main_layout.addWidget(self.tabs, stretch=1)

    def _init_traffic_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)

        stats_box = QGroupBox("Thông số giám sát hiện tại")
        stats_layout = QGridLayout(stats_box)

        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(11)

        stats_layout.addWidget(QLabel("Giao diện mạng:"), 0, 0)
        self.lbl_interface = QLabel("Chưa xác định")
        self.lbl_interface.setFont(bold_font)
        stats_layout.addWidget(self.lbl_interface, 0, 1)

        stats_layout.addWidget(QLabel("Tốc độ Upload (Gửi):"), 0, 2)
        self.lbl_upload_speed = QLabel("Chưa có dữ liệu")
        self.lbl_upload_speed.setFont(bold_font)
        self.lbl_upload_speed.setStyleSheet("color: #d9534f;")
        stats_layout.addWidget(self.lbl_upload_speed, 0, 3)

        stats_layout.addWidget(QLabel("Tốc độ Download (Nhận):"), 1, 0)
        self.lbl_download_speed = QLabel("Chưa có dữ liệu")
        self.lbl_download_speed.setFont(bold_font)
        stats_layout.addWidget(self.lbl_download_speed, 1, 1)

        stats_layout.addWidget(QLabel("Tổng dung lượng (Gửi / Nhận):"), 1, 2)
        self.lbl_total_bytes = QLabel("Chưa có dữ liệu")
        self.lbl_total_bytes.setFont(bold_font)
        stats_layout.addWidget(self.lbl_total_bytes, 1, 3)

        layout.addWidget(stats_box)

        graph_box = QGroupBox("Biểu đồ tốc độ băng thông thời gian thực (KB/s)")
        graph_layout = QVBoxLayout(graph_box)

        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel("left", "Tốc độ", units="KB/s")
        self.plot_widget.setLabel("bottom", "Thời gian", units="mẫu")
        self.plot_widget.addLegend()

        self.curve_upload = self.plot_widget.plot(
            pen=pg.mkPen(color="#d9534f", width=2), name="Upload (KB/s)", connect="finite"
        )
        self.curve_download = self.plot_widget.plot(
            pen=pg.mkPen(color="#0275d8", width=2), name="Download (KB/s)", connect="finite"
        )
        graph_layout.addWidget(self.plot_widget)

        layout.addWidget(graph_box, stretch=2)

        log_box = QGroupBox("Nhật ký sự kiện hệ thống")
        log_layout = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_box, stretch=1)

    def _init_capture_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)

        cap_ctrl_box = QGroupBox("Điều khiển Packet Capture (Scapy / Npcap)")
        cap_ctrl_layout = QHBoxLayout(cap_ctrl_box)

        self.btn_start_capture = QPushButton("Bắt đầu Capture")
        self.btn_start_capture.setStyleSheet("font-weight: bold; background-color: #5cb85c; color: white;")
        self.btn_start_capture.clicked.connect(self._start_capture)
        cap_ctrl_layout.addWidget(self.btn_start_capture)

        self.btn_stop_capture = QPushButton("Dừng Capture")
        self.btn_stop_capture.setStyleSheet("font-weight: bold; background-color: #d9534f; color: white;")
        self.btn_stop_capture.setEnabled(False)
        self.btn_stop_capture.clicked.connect(self._stop_capture)
        cap_ctrl_layout.addWidget(self.btn_stop_capture)

        self.lbl_capture_info = QLabel("Trạng thái Sniffer: Đang dừng | Số gói: 0")
        self.lbl_capture_info.setStyleSheet("font-weight: bold; margin-left: 10px;")
        cap_ctrl_layout.addWidget(self.lbl_capture_info)
        cap_ctrl_layout.addStretch()

        layout.addWidget(cap_ctrl_box)

        table_box = QGroupBox("Danh sách Gói tin Mạng (Packet Ring Buffer)")
        table_layout = QVBoxLayout(table_box)

        # Mở rộng bảng lên 9 cột để chứa cột Tiến trình (.exe)
        self.packet_table = QTableWidget(0, 9)
        self.packet_table.setHorizontalHeaderLabels([
            "#",
            "Thời gian (UTC)",
            "Tiến trình (.exe)",
            "IP Nguồn",
            "Cổng Nguồn",
            "IP Đích",
            "Cổng Đích",
            "Giao thức",
            "Độ dài (Bytes)",
        ])
        self.packet_table.verticalHeader().setVisible(False)
        self.packet_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.packet_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.packet_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.packet_table.itemSelectionChanged.connect(self._on_packet_selected)
        table_layout.addWidget(self.packet_table)

        layout.addWidget(table_box, stretch=2)

        inspect_box = QGroupBox("Phân tích Chi tiết Gói tin được chọn (Deep Inspection)")
        inspect_layout = QVBoxLayout(inspect_box)

        self.inspect_text = QTextEdit()
        self.inspect_text.setReadOnly(True)
        self.inspect_text.setPlaceholderText(
            "Nhấp chọn một dòng gói tin ở bảng trên để xem phân tích chi tiết các tầng mạng..."
        )
        inspect_layout.addWidget(self.inspect_text)

        layout.addWidget(inspect_box, stretch=1)

    def _init_analytics_tab(self, parent: QWidget) -> None:
        layout = QHBoxLayout(parent)

        proto_box = QGroupBox("Phân tích Tỷ lệ Giao thức (Protocol Breakdown)")
        proto_layout = QVBoxLayout(proto_box)

        self.lbl_total_analyzed = QLabel("Tổng số gói tin đã phân tích: 0")
        self.lbl_total_analyzed.setStyleSheet("font-weight: bold;")
        proto_layout.addWidget(self.lbl_total_analyzed)

        self.proto_table = QTableWidget(0, 3)
        self.proto_table.setHorizontalHeaderLabels(["Giao thức", "Số gói tin", "Tỷ lệ (%)"])
        self.proto_table.verticalHeader().setVisible(False)
        self.proto_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.proto_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        proto_layout.addWidget(self.proto_table)

        layout.addWidget(proto_box, stretch=1)

        talkers_box = QGroupBox("Top Talkers (Các địa chỉ IP chiếm lưu lượng lớn nhất)")
        talkers_layout = QVBoxLayout(talkers_box)

        talkers_layout.addWidget(QLabel("Top 5 IP Gửi dữ liệu nhiều nhất (Top Senders):"))
        self.top_senders_table = QTableWidget(0, 3)
        self.top_senders_table.setHorizontalHeaderLabels(["IP Nguồn", "Số gói tin", "Dung lượng"])
        self.top_senders_table.verticalHeader().setVisible(False)
        self.top_senders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.top_senders_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        talkers_layout.addWidget(self.top_senders_table)

        talkers_layout.addWidget(QLabel("Top 5 IP Nhận dữ liệu nhiều nhất (Top Receivers):"))
        self.top_receivers_table = QTableWidget(0, 3)
        self.top_receivers_table.setHorizontalHeaderLabels(["IP Đích", "Số gói tin", "Dung lượng"])
        self.top_receivers_table.verticalHeader().setVisible(False)
        self.top_receivers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.top_receivers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        talkers_layout.addWidget(self.top_receivers_table)

        layout.addWidget(talkers_box, stretch=1)

    def _init_alerts_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)

        cfg_box = QGroupBox("Thiết lập Ngưỡng Cảnh báo Tốc độ (Threshold Alerting Rules)")
        cfg_layout = QHBoxLayout(cfg_box)

        cfg_layout.addWidget(QLabel("Ngưỡng Upload tối đa (KB/s):"))
        self.spin_max_up = QDoubleSpinBox()
        self.spin_max_up.setRange(0.0, 1_000_000.0)
        self.spin_max_up.setSingleStep(10.0)
        self.spin_max_up.setValue(0.0)
        self.spin_max_up.setToolTip("0 = Không đặt giới hạn cảnh báo Upload")
        cfg_layout.addWidget(self.spin_max_up)

        cfg_layout.addWidget(QLabel("Ngưỡng Download tối đa (KB/s):"))
        self.spin_max_down = QDoubleSpinBox()
        self.spin_max_down.setRange(0.0, 1_000_000.0)
        self.spin_max_down.setSingleStep(10.0)
        self.spin_max_down.setValue(0.0)
        self.spin_max_down.setToolTip("0 = Không đặt giới hạn cảnh báo Download")
        cfg_layout.addWidget(self.spin_max_down)

        self.chk_alert_enabled = QCheckBox("Bật Động cơ Cảnh báo")
        self.chk_alert_enabled.setChecked(True)
        cfg_layout.addWidget(self.chk_alert_enabled)

        self.btn_save_alert_cfg = QPushButton("Lưu Cấu hình")
        self.btn_save_alert_cfg.setStyleSheet("font-weight: bold; background-color: #0275d8; color: white;")
        self.btn_save_alert_cfg.clicked.connect(self._save_alert_config)
        cfg_layout.addWidget(self.btn_save_alert_cfg)

        layout.addWidget(cfg_box)

        history_box = QGroupBox("Nhật ký Lịch sử Sự kiện Cảnh báo (Alert History)")
        history_layout = QVBoxLayout(history_box)

        self.alert_table = QTableWidget(0, 5)
        self.alert_table.setHorizontalHeaderLabels([
            "Mốc thời gian (UTC)", "Loại Cảnh báo", "Tốc độ Thực tế", "Ngưỡng Quy định", "Nội dung Thông báo"
        ])
        self.alert_table.verticalHeader().setVisible(False)
        self.alert_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.alert_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self.alert_table)

        layout.addWidget(history_box, stretch=1)

    def _save_alert_config(self) -> None:
        if self.worker and self.worker.isRunning():
            up_kb = self.spin_max_up.value()
            down_kb = self.spin_max_down.value()
            enabled = self.chk_alert_enabled.isChecked()

            rule_data = {
                "max_upload_bytes_per_sec": (up_kb * 1000.0) if up_kb > 0 else None,
                "max_download_bytes_per_sec": (down_kb * 1000.0) if down_kb > 0 else None,
                "enabled": enabled,
            }
            self.worker.set_alert_config_request(rule_data)

    @pyqtSlot(dict)
    def _on_alert_config_received(self, cfg: Dict[str, Any]) -> None:
        max_up_bytes = cfg.get("max_upload_bytes_per_sec")
        max_down_bytes = cfg.get("max_download_bytes_per_sec")
        enabled = cfg.get("enabled", True)

        self.spin_max_up.setValue((max_up_bytes / 1000.0) if max_up_bytes else 0.0)
        self.spin_max_down.setValue((max_down_bytes / 1000.0) if max_down_bytes else 0.0)
        self.chk_alert_enabled.setChecked(enabled)

    @pyqtSlot(list)
    def _on_alert_history_updated(self, alerts: List[Dict[str, Any]]) -> None:
        self.alert_table.setRowCount(0)
        for event in alerts:
            row = self.alert_table.rowCount()
            self.alert_table.insertRow(row)

            ts_str = event.get("timestamp", "")
            if "T" in ts_str:
                ts_str = ts_str.split("T")[1].replace("Z", "")[:8]

            alert_type = event.get("alert_type", "exceeded")
            cur_val = event.get("current_value", 0.0)
            thresh_val = event.get("threshold_value", 0.0)
            msg = event.get("message", "")

            item_ts = QTableWidgetItem(ts_str)
            item_type = QTableWidgetItem("Vượt Upload" if alert_type == "upload_exceeded" else "Vượt Download")
            item_cur = QTableWidgetItem(format_bytes_speed(cur_val))
            item_thresh = QTableWidgetItem(format_bytes_speed(thresh_val))
            item_msg = QTableWidgetItem(msg)

            item_type.setForeground(QColor("#d9534f"))
            item_msg.setForeground(QColor("#d9534f"))

            self.alert_table.setItem(row, 0, item_ts)
            self.alert_table.setItem(row, 1, item_type)
            self.alert_table.setItem(row, 2, item_cur)
            self.alert_table.setItem(row, 3, item_thresh)
            self.alert_table.setItem(row, 4, item_msg)

    def _start_capture(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.start_capture_request()

    def _stop_capture(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop_capture_request()

    @pyqtSlot(dict)
    def _on_capture_status_changed(self, status: Dict[str, Any]) -> None:
        is_running = status.get("is_running", False)
        iface = status.get("interface", "Chưa rõ")
        count = status.get("packet_count", 0)

        if is_running:
            self.lbl_capture_info.setText(f"Trạng thái Sniffer: Đang chạy ({iface}) | Số gói: {count}")
            self.lbl_capture_info.setStyleSheet("font-weight: bold; color: green;")
            self.btn_start_capture.setEnabled(False)
            self.btn_stop_capture.setEnabled(True)
        else:
            self.lbl_capture_info.setText(f"Trạng thái Sniffer: Đang dừng | Số gói thu thập: {count}")
            self.lbl_capture_info.setStyleSheet("font-weight: bold; color: gray;")
            self.btn_start_capture.setEnabled(True)
            self.btn_stop_capture.setEnabled(False)

    @pyqtSlot(list)
    def _on_packets_captured(self, packets: List[Dict[str, Any]]) -> None:
        self.captured_packets_data = packets
        self.packet_table.setRowCount(0)

        for idx, pkt in enumerate(packets):
            row = self.packet_table.rowCount()
            self.packet_table.insertRow(row)

            ts_str = pkt.get("timestamp", "")
            if "T" in ts_str:
                ts_str = ts_str.split("T")[1].replace("Z", "")[:8]

            proc_name = str(pkt.get("process_name") or "Unknown / System")
            src_port = str(pkt.get("src_port") or "-")
            dst_port = str(pkt.get("dst_port") or "-")

            self.packet_table.setItem(row, 0, QTableWidgetItem(str(idx + 1)))
            self.packet_table.setItem(row, 1, QTableWidgetItem(ts_str))

            proc_item = QTableWidgetItem(proc_name)
            proc_item.setForeground(QColor("#0275d8"))
            self.packet_table.setItem(row, 2, proc_item)

            self.packet_table.setItem(row, 3, QTableWidgetItem(str(pkt.get("src_ip", "-"))))
            self.packet_table.setItem(row, 4, QTableWidgetItem(src_port))
            self.packet_table.setItem(row, 5, QTableWidgetItem(str(pkt.get("dst_ip", "-"))))
            self.packet_table.setItem(row, 6, QTableWidgetItem(dst_port))
            self.packet_table.setItem(row, 7, QTableWidgetItem(str(pkt.get("protocol", "-"))))

            len_item = QTableWidgetItem(str(pkt.get("length_bytes", 0)))
            len_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.packet_table.setItem(row, 8, len_item)

    @pyqtSlot(dict)
    def _on_analytics_updated(self, analytics: Dict[str, Any]) -> None:
        total = analytics.get("total_packets_analyzed", 0)
        self.lbl_total_analyzed.setText(f"Tổng số gói tin đã phân tích: {total}")

        protocols = analytics.get("protocols", [])
        self.proto_table.setRowCount(0)
        for p in protocols:
            row = self.proto_table.rowCount()
            self.proto_table.insertRow(row)
            proto_name = p.get("protocol", "OTHER")
            cnt = p.get("packet_count", 0)
            pct = p.get("percentage", 0.0)
            self.proto_table.setItem(row, 0, QTableWidgetItem(str(proto_name)))
            self.proto_table.setItem(row, 1, QTableWidgetItem(str(cnt)))
            self.proto_table.setItem(row, 2, QTableWidgetItem(f"{pct:.1f}%"))

        top_senders = analytics.get("top_senders", [])
        self.top_senders_table.setRowCount(0)
        for s in top_senders:
            row = self.top_senders_table.rowCount()
            self.top_senders_table.insertRow(row)
            self.top_senders_table.setItem(row, 0, QTableWidgetItem(str(s.get("ip"))))
            self.top_senders_table.setItem(row, 1, QTableWidgetItem(str(s.get("packet_count"))))
            self.top_senders_table.setItem(row, 2, QTableWidgetItem(format_bytes_total(s.get("total_bytes"))))

        top_receivers = analytics.get("top_receivers", [])
        self.top_receivers_table.setRowCount(0)
        for r in top_receivers:
            row = self.top_receivers_table.rowCount()
            self.top_receivers_table.insertRow(row)
            self.top_receivers_table.setItem(row, 0, QTableWidgetItem(str(r.get("ip"))))
            self.top_receivers_table.setItem(row, 1, QTableWidgetItem(str(r.get("packet_count"))))
            self.top_receivers_table.setItem(row, 2, QTableWidgetItem(format_bytes_total(r.get("total_bytes"))))

    def _on_packet_selected(self) -> None:
        selected_rows = self.packet_table.selectedItems()
        if not selected_rows:
            return
        row_index = selected_rows[0].row()
        if 0 <= row_index < len(self.captured_packets_data):
            pkt = self.captured_packets_data[row_index]
            self._render_deep_inspection(pkt, row_index + 1)

    def _render_deep_inspection(self, pkt: Dict[str, Any], packet_num: int) -> None:
        proto = pkt.get("protocol", "UNKNOWN")
        src_ip = pkt.get("src_ip", "0.0.0.0")
        dst_ip = pkt.get("dst_ip", "0.0.0.0")
        src_port = pkt.get("src_port")
        dst_port = pkt.get("dst_port")
        length = pkt.get("length_bytes", 0)
        ts = pkt.get("timestamp", "")
        proc_name = pkt.get("process_name") or "Chưa xác định"
        proc_id = pkt.get("process_id") or "N/A"

        detail = [
            f"=== GÓI TIN MẠNG #{packet_num} ===",
            f"Mốc thời gian (ISO 8601 UTC): {ts}",
            f"Tổng độ dài khung gói tin (Frame Length): {length} bytes ({length * 8} bits)",
            "",
            "--- THÔNG TIN TIẾN TRÌNH HỆ THỐNG (PROCESS INFO) ---",
            f"  * Tên Tiến trình (.exe): {proc_name}",
            f"  * Mã Tiến trình (PID): {proc_id}",
            "",
            "--- TẦNG MẠNG (NETWORK LAYER / INTERNET PROTOCOL) ---",
            f"  * Phiên bản / Giao thức: {proto}",
            f"  * Địa chỉ IP Nguồn (Source IP): {src_ip}",
            f"  * Địa chỉ IP Đích (Destination IP): {dst_ip}",
            "",
            "--- TẦNG VẬN CHUYỂN (TRANSPORT LAYER) ---",
        ]

        if src_port is not None or dst_port is not None:
            detail.append(f"  * Cổng Nguồn (Source Port): {src_port or 'Không rõ'}")
            detail.append(f"  * Cổng Đích (Destination Port): {dst_port or 'Không rõ'}")
            if dst_port in (80, 8080):
                detail.append("  * Ứng dụng gợi ý: HTTP (Unencrypted Web Traffic)")
            elif dst_port == 443:
                detail.append("  * Ứng dụng gợi ý: HTTPS / TLS (Encrypted Web Traffic)")
            elif dst_port == 53:
                detail.append("  * Ứng dụng gợi ý: DNS (Domain Name System Queries)")
        else:
            detail.append("  * Giao thức không sử dụng khái niệm Cổng (Port-less protocol / ICMP).")

        self.inspect_text.setText("\n".join(detail))

    def _toggle_connection(self) -> None:
        if self.worker and self.worker.isRunning():
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        host = self.host_input.text().strip()
        port = self.port_input.value()

        self.btn_connect.setText("Đang kết nối...")
        self.btn_connect.setEnabled(False)

        self.worker = ClientWorker(host, port)
        self.worker.status_changed.connect(self._on_status_changed)
        self.worker.traffic_updated.connect(self._on_traffic_updated)
        self.worker.server_status_updated.connect(self._on_server_status_updated)
        self.worker.resynced.connect(self._on_resynced)
        self.worker.log_message.connect(self._on_log_message)
        self.worker.packets_captured.connect(self._on_packets_captured)
        self.worker.capture_status_changed.connect(self._on_capture_status_changed)
        self.worker.analytics_updated.connect(self._on_analytics_updated)
        self.worker.alert_history_updated.connect(self._on_alert_history_updated)
        self.worker.alert_config_received.connect(self._on_alert_config_received)
        self.worker.start()

    def _disconnect(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None

        self.btn_connect.setText("Kết nối")
        self.btn_connect.setEnabled(True)
        self.lbl_status.setText("Trạng thái: Chưa kết nối")
        self.lbl_status.setStyleSheet("font-weight: bold; color: gray;")
        self._on_log_message("[HỆ THỐNG] Đã ngắt kết nối theo yêu cầu người dùng.")

    @pyqtSlot(str, str)
    def _on_status_changed(self, status_code: str, message: str) -> None:
        if status_code in ("ws_connected", "http_ok"):
            self.lbl_status.setText("Trạng thái: Đã kết nối")
            self.lbl_status.setStyleSheet("font-weight: bold; color: green;")
            self.btn_connect.setText("Ngắt kết nối")
            self.btn_connect.setEnabled(True)
        elif status_code in ("ws_connecting", "resyncing"):
            self.lbl_status.setText(f"Trạng thái: {message}")
            self.lbl_status.setStyleSheet("font-weight: bold; color: orange;")
        elif status_code in ("ws_disconnected", "http_error"):
            self.lbl_status.setText("Trạng thái: Lỗi / Mất kết nối")
            self.lbl_status.setStyleSheet("font-weight: bold; color: red;")
            self.btn_connect.setText("Thử lại / Ngắt")
            self.btn_connect.setEnabled(True)
            self._add_gap_to_plot()

    def _add_gap_to_plot(self) -> None:
        if self.upload_history and not np.isnan(self.upload_history[-1]):
            self.upload_history.append(np.nan)
            self.download_history.append(np.nan)

            if len(self.upload_history) > self.history_limit:
                self.upload_history.pop(0)
                self.download_history.pop(0)

            self.curve_upload.setData(np.array(self.upload_history))
            self.curve_download.setData(np.array(self.download_history))

    @pyqtSlot(dict)
    def _on_traffic_updated(self, data: Dict[str, Any]) -> None:
        iface = data.get("interface", "Không rõ")
        up_speed = data.get("upload_bytes_per_second")
        down_speed = data.get("download_bytes_per_second")
        total_sent = data.get("total_sent_bytes")
        total_recv = data.get("total_received_bytes")

        self.lbl_interface.setText(iface)
        self.lbl_upload_speed.setText(format_bytes_speed(up_speed))
        self.lbl_download_speed.setText(format_bytes_speed(down_speed))
        self.lbl_total_bytes.setText(f"{format_bytes_total(total_sent)} / {format_bytes_total(total_recv)}")

        up_kb = (up_speed / 1000.0) if up_speed is not None else 0.0
        down_kb = (down_speed / 1000.0) if down_speed is not None else 0.0

        self.upload_history.append(up_kb)
        self.download_history.append(down_kb)

        if len(self.upload_history) > self.history_limit:
            self.upload_history.pop(0)
            self.download_history.pop(0)

        self.curve_upload.setData(np.array(self.upload_history))
        self.curve_download.setData(np.array(self.download_history))

    @pyqtSlot(dict)
    def _on_server_status_updated(self, data: Dict[str, Any]) -> None:
        status = data.get("status", "unknown")
        iface = data.get("interface", "Chưa xác định")
        msg = f"[SERVER STATUS] Dịch vụ: {status} | Giao diện: {iface}"
        self._on_log_message(msg)

    @pyqtSlot(dict)
    def _on_resynced(self, data: Dict[str, Any]) -> None:
        health = data.get("health", {})
        interfaces = data.get("interfaces", [])
        self._on_log_message(
            f"[RESYNC SUCCESS] Đã đồng bộ lại {len(interfaces)} giao diện từ Server (Trạng thái: {health.get('status')})"
        )

    @pyqtSlot(str)
    def _on_log_message(self, message: str) -> None:
        self.log_text.append(message)

    def closeEvent(self, event) -> None:
        self._disconnect()
        event.accept()

def run_client_gui(host: str = "127.0.0.1", port: int = 8000) -> None:
    app = QApplication(sys.argv)
    window = MainWindow(default_host=host, default_port=port)
    window.show()
    sys.exit(app.exec())
    