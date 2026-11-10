# Network Traffic Monitor (Giám sát Lưu lượng Mạng)

Hệ thống ứng dụng Client - Server đa luồng giám sát và phân tích lưu lượng mạng thời gian thực trên Windows sử dụng **Python 3.10+**, **FastAPI**, **PyQt6**, **pyqtgraph**, và **Scapy**.

---

## Tính năng chính

1. **Giám sát Lưu lượng Thời gian thực (Realtime Traffic Monitoring):**
   - Đo tốc độ Upload/Download (KB/s, MB/s) và tổng dung lượng tích lũy theo chu kỳ lấy mẫu cố định.
   - Trực quan hóa dữ liệu bằng biểu đồ đường sóng mượt mà với `pyqtgraph`.

2. **Cơ chế Reconnect & Resync Tự động (Client Resync):**
   - Tự động kết nối lại theo thuật toán Exponential Backoff ($1s, 2s, 4s, 8s...$) khi mất kết nối.
   - Chèn mốc `np.nan` để ngắt nét vẽ nét đứt trên biểu đồ khi rớt mạng.
   - Tự động gọi HTTP REST API để đồng bộ lại trạng thái Server và danh sách Interface khi WebSocket phục hồi.

3. **Packet Capture & Phân tích Gói tin (Scapy / Npcap):**
   - Bắt gói tin thời gian thực ở mức Kernel driver qua Npcap.
   - Trích xuất Metadata gói tin (IP Nguồn/Đích, Port, Protocol TCP/UDP/ICMP, Length) lưu trong bộ nhớ đệm Ring Buffer (1000 gói).

4. **Phân tích Giao thức & Top Talkers:**
   - Thống kê tỷ lệ phân bố % các giao thức mạng.
   - Xếp hạng Top 5 / Top 10 IP gửi và nhận nhiều dữ liệu nhất.

5. **Động cơ Cảnh báo Ngưỡng Băng thông (Traffic Alert Engine):**
   - Đặt ngưỡng tốc độ Upload / Download tối đa.
   - Đẩy sự kiện cảnh báo đỏ tức thì khi băng thông vượt quá ngưỡng thiết lập.

6. **Giao diện Quản trị Server GUI (PyQt6 trên Host):**
   - Quản lý khởi động / dừng dịch vụ Uvicorn ASGI trong luồng phụ (`QThread`).
   - Tự động chuyển hướng Python logging chảy trực tiếp vào Console GUI.

---

## Yêu cầu Hệ thống

- **Hệ điều hành:** Windows 10 / Windows 11.
- **Python:** Phiên bản 3.10 trở lên (khuyên dùng Python 3.13).
- **Driver Npcap:** Cần cài đặt [Npcap](https://npcap.com/) (chế độ WinPcap API-compatible) để sử dụng tính năng Packet Capture.
- **Quyền hạn:** Mở Terminal / PowerShell dưới quyền **Run as Administrator** khi chạy Server để Scapy truy cập card mạng.

---

## Cài đặt Môi trường

1. **Cloning / Tải mã nguồn dự án:**
   ```powershell
   git clone [https://github.com/nhdkn16/networking-traffic-monitor.git](https://github.com/nhdkn16/networking-traffic-monitor.git)
   cd networking-traffic-monitor
