# Network Monitor

Giám sát lưu lượng mạng theo thời gian thực bằng HTTP và WebSocket (mô hình Client-Server, Host - Guest VirtualBox).

> **Trạng thái:** Giai đoạn 4 - đã có Collector (psutil), lệnh chẩn đoán `collect`, HTTP API và WebSocket (FastAPI).
> Chưa có giao diện. Xem `CLAUDE.md` mục 15 để biết trạng thái đã được kiểm chứng.

## Yêu cầu

- Python 3.10 trở lên (đang dùng 3.13 trên Host Windows 11)

## Cài đặt (PowerShell, tại thư mục gốc dự án)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu PowerShell chặn script kích hoạt venv:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Chạy

```powershell
python main.py --help
python main.py server   # HTTP API trên Host (chưa có Server GUI)
python main.py client   # chưa triển khai
```

### Server HTTP API (`server`)

```powershell
python main.py server                                   # http://127.0.0.1:8000 (chỉ máy Host truy cập được)
python main.py server --host 0.0.0.0 --port 8000        # cho Guest truy cập (mạng lab, chưa có xác thực)
python main.py server --interface "Wi-Fi"               # chỉ định interface giám sát
```

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/health` | Trạng thái Server (`ok` hoặc `degraded`), phiên bản, thời gian chạy, số Client WebSocket |
| GET | `/api/interfaces` | Danh sách interface; thêm `?include_all=true` để xem cả loopback/ngắt kết nối |
| GET | `/api/statistics/current` | Mẫu lưu lượng mới nhất; trả **503** nếu chưa có dữ liệu (không trả số 0 giả) |

Trang tài liệu và thử API trực tiếp: `http://127.0.0.1:8000/docs`.

Thử bằng PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/interfaces
Invoke-RestMethod http://127.0.0.1:8000/api/statistics/current
```

Biến môi trường (tùy chọn): `NETWORK_MONITOR_HOST`, `NETWORK_MONITOR_PORT`,
`NETWORK_MONITOR_INTERVAL` (chu kỳ lấy mẫu, giây), `NETWORK_MONITOR_INTERFACE`,
`NETWORK_MONITOR_MAX_WS_CLIENTS` (số Client WebSocket tối đa, mặc định 20).
Tham số dòng lệnh ghi đè biến môi trường.

Tốc độ do một tác vụ nền lấy mẫu mỗi chu kỳ; vài giây đầu sau khi khởi động API trả 503.

### WebSocket (`/ws`)

Server chủ động đẩy dữ liệu thật tới mọi Client đang kết nối: `ws://127.0.0.1:8000/ws`.
Mọi message có dạng `{"type": ..., "timestamp": "...Z", "data": {...}}` (timestamp là UTC).

| Hướng | `type` | Khi nào |
|---|---|---|
| Server → Client | `server_status` | Ngay khi kết nối, và mỗi khi trạng thái đổi giữa `ok` và `degraded` |
| Server → Client | `traffic_update` | Mỗi khi có mẫu mới (theo chu kỳ lấy mẫu, mặc định 1 giây) |
| Server → Client | `pong` | Phản hồi `ping` |
| Server → Client | `error` | Client gửi message sai (kết nối vẫn giữ); `data.code`: `invalid_json`, `invalid_message`, `unknown_type`, `binary_not_supported`, `message_too_large` |
| Client → Server | `ping` | Tùy chọn, để kiểm tra kết nối |

Đơn vị: `*_bytes_per_second` là byte/giây; `total_*_bytes` là byte tích lũy. Client chậm hoặc
lỗi (gửi quá 2 giây không xong) bị ngắt; vượt giới hạn số Client thì bị đóng với mã 1013.

Xem message bằng công cụ độc lập (chỉ cần thư viện `websockets`, có thể chép riêng sang Guest):

```powershell
python tools/ws_listen.py
python tools/ws_listen.py --url ws://192.168.56.1:8000/ws --count 10
python tools/ws_listen.py --raw --ping-interval 5
```

### Chẩn đoán Collector (`collect`)

Đọc bộ đếm thật của máy đang chạy lệnh và in tốc độ gửi/nhận mỗi chu kỳ.
Quy ước hiển thị: hệ số 1000 (KB/s, MB/s), kèm Mbps (1 byte = 8 bit).

```powershell
python main.py collect --list                 # interface đang hoạt động
python main.py collect --list --all           # gồm cả interface ngắt kết nối và loopback
python main.py collect                        # tự chọn interface, Ctrl+C để dừng
python main.py collect --interface "Wi-Fi" --interval 1 --count 10
```

Tên interface có dấu cách hoặc dấu gạch nối cần đặt trong dấu nháy kép.
Tốc độ là trung bình kể từ lần lấy mẫu trước; lần đọc đầu tiên chỉ dùng làm mốc nên không in.

## Kiểm thử

```powershell
python -m pytest -v
```
