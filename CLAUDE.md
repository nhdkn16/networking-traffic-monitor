# CLAUDE.md --- Network Monitor

# Dự án: Sử dụng giao thức HTTP và WebSocket để giám sát lưu lượng mạng theo thời gian thực

> Tài liệu định hướng dành cho Claude và các AI coding assistant khi đọc, phân tích, thiết kế, tạo mới hoặc chỉnh sửa mã nguồn dự án.
>
> **Trạng thái hiện tại:** Dự án bắt đầu từ đầu. Các chức năng, cấu trúc thư mục và công nghệ bên dưới là định hướng thiết kế, chưa được xem là đã triển khai. Khi làm việc với source code thực tế, hãy kiểm tra trước khi kết luận.

---

## 1. Tổng quan dự án

### 1.1. Tên đề tài

**Sử dụng giao thức HTTP và WebSocket để giám sát lưu lượng mạng theo thời gian thực**

Tên ứng dụng dự kiến: **Network Monitor**

### 1.2. Mục tiêu

Xây dựng ứng dụng Python theo mô hình Client–Server để thu thập, truyền tải, hiển thị và phân tích thông tin lưu lượng mạng theo thời gian thực.

Hệ thống cần có giao diện đồ họa trên cả hai phía:

- **Host – Server:** Máy thật chạy dịch vụ thu thập dữ liệu mạng, quản lý kết nối Client, cung cấp API và có giao diện quản trị/giám sát Server.
- **Guest – Client:** Máy ảo chạy ứng dụng Client, kết nối đến Server qua mạng ảo để nhận và hiển thị dữ liệu giám sát.

Mục tiêu học tập chính là hiểu và áp dụng đúng mô hình Client–Server, HTTP, WebSocket, thu thập dữ liệu mạng, lập trình Python và xây dựng giao diện.

### 1.3. Phạm vi

Các chức năng dự kiến:

1. Phát hiện và liệt kê card mạng trên Host.
2. Thu thập thống kê lưu lượng gửi/nhận theo giao diện mạng.
3. Hiển thị tốc độ upload/download theo thời gian thực.
4. Thu thập metadata gói tin khi được cấu hình và cấp quyền phù hợp.
5. Thống kê giao thức mạng như IPv4, IPv6, TCP, UDP, ICMP, DNS, HTTP và HTTPS khi có thể nhận diện.
6. Phân tích các kết nối/luồng giao tiếp nguồn – đích (Top Talkers).
7. Cảnh báo khi lưu lượng vượt ngưỡng cấu hình.
8. Server cung cấp dữ liệu và trạng thái thông qua HTTP API và WebSocket.
9. Client kết nối, nhận dữ liệu và hiển thị thông tin trên máy ảo.
10. Server có giao diện riêng để theo dõi trạng thái dịch vụ, Client kết nối và hoạt động thu thập dữ liệu.

Không được tuyên bố đã hoàn thành chức năng nào nếu chưa kiểm tra và chạy thử.

---

## 2. Mô hình triển khai Client–Server

### 2.1. Sơ đồ logic

```text
                  HOST – MÁY THẬT (Windows)
+----------------------------------------------------------+
|                                                          |
|  +----------------------+     +-----------------------+  |
|  | Network Collector    |---->|                       |  |
|  | psutil               |     |                       |  |
|  +----------------------+     |                       |  |
|                               |   FastAPI Server      |  |
|  +----------------------+     |   HTTP + WebSocket    |  |
|  | Packet Capture       |---->|                       |  |
|  | Scapy / Npcap        |     |                       |  |
|  +----------------------+     +-----------+-----------+  |
|                                           |              |
|                               +-----------v-----------+  |
|                               | Server GUI            |  |
|                               | Trạng thái, cấu hình,  |  |
|                               | Client, log, capture  |  |
|                               +-----------------------+  |
+-------------------------------------------|--------------+
                                            |
                              VirtualBox Host-only Network
                                            |
                     HTTP REST + WebSocket |
                                            |
                  GUEST – MÁY ẢO (Windows/Linux)
+-------------------------------------------v--------------+
|                                                          |
|  +----------------------+     +-----------------------+  |
|  | HTTP API Client      |     | WebSocket Client      |  |
|  | Lấy cấu hình,        |     | Nhận dữ liệu realtime |  |
|  | gửi lệnh, truy vấn   |     | và trạng thái         |  |
|  +----------------------+     +-----------------------+  |
|                 \                  /                     |
|                  \                /                      |
|                   +--------------+                       |
|                   | Client GUI   |                       |
|                   | Dashboard    |                       |
|                   +--------------+                       |
+----------------------------------------------------------+
```

### 2.2. Host – Server

Host là nơi trực tiếp quan sát các giao diện mạng vật lý/ảo của máy thật.

Nhiệm vụ:

- Liệt kê network interfaces.
- Thu thập số byte gửi/nhận, tốc độ gửi/nhận và các thống kê liên quan.
- Thực hiện packet capture nếu người dùng bật tính năng và hệ điều hành cho phép.
- Phân tích metadata gói tin/luồng mạng.
- Duy trì trạng thái giám sát và ngưỡng cảnh báo.
- Cung cấp HTTP API cho các thao tác yêu cầu – phản hồi.
- Cung cấp WebSocket để đẩy dữ liệu liên tục đến Client.
- Quản lý nhiều Client kết nối, ngắt kết nối và trạng thái kết nối.
- Ghi log hoạt động và lỗi.
- Cung cấp giao diện Server GUI để người vận hành theo dõi trạng thái hệ thống, cấu hình, giao diện mạng, trạng thái capture, Client và log.

Server GUI là giao diện quản trị cục bộ trên Host; không thay thế FastAPI Server và không phải là Client GUI.

### 2.3. Guest – Client

Guest là máy ảo chạy ứng dụng Client. Client không trực tiếp capture lưu lượng trên Host.

Nhiệm vụ:

- Cấu hình địa chỉ IP và cổng của Server.
- Kiểm tra kết nối đến Server.
- Gọi HTTP API để lấy danh sách interface, cấu hình và trạng thái ban đầu.
- Mở WebSocket để nhận dữ liệu giám sát theo thời gian thực.
- Hiển thị biểu đồ, thống kê giao thức, Top Talkers và cảnh báo.
- Cho phép người dùng chọn interface hoặc gửi lệnh điều khiển được Server hỗ trợ.
- Hiển thị trạng thái kết nối, thời điểm cập nhật và lỗi kết nối.
- Tự kết nối lại theo chiến lược có giới hạn khi mất kết nối.

Client chỉ được hiển thị hoặc gửi yêu cầu trong phạm vi API Server cung cấp. Không tự ý truy cập trực tiếp dữ liệu nội bộ của Host.

### 2.4. Mạng giữa Host và Guest

Môi trường phát triển dự kiến sử dụng VirtualBox:

- Host chạy Server.
- Guest chạy Client.
- Có thể cấu hình Adapter 1 là NAT để Guest truy cập Internet.
- Cấu hình Adapter 2 là Host-only để Guest giao tiếp riêng với Host.
- IP Host-only của Host và Guest phải được kiểm tra bằng `ipconfig` (Windows) hoặc `ip addr` (Linux), không được mặc định IP nếu chưa xác minh.
- Server cần bind vào địa chỉ phù hợp, thường là `0.0.0.0` trong môi trường lab, để Guest truy cập được.
- Firewall trên Host phải cho phép kết nối đến cổng Server trong mạng lab.

Địa chỉ ví dụ chỉ để minh họa, không phải cấu hình cố định:

```text
Host Host-only IP: 192.168.56.1
Guest Host-only IP: 192.168.56.101
HTTP base URL:     http://192.168.56.1:8000
WebSocket URL:     ws://192.168.56.1:8000/ws
```

Không mở dịch vụ giám sát ra Internet công cộng nếu chưa có xác thực, mã hóa và biện pháp bảo vệ phù hợp.

---

## 3. Lựa chọn giao thức truyền thông

### 3.1. HTTP REST API

Sử dụng HTTP cho các yêu cầu có tính chất truy vấn hoặc điều khiển, ví dụ:

- Kiểm tra Server có hoạt động không.
- Lấy thông tin hệ thống.
- Lấy danh sách network interfaces.
- Lấy cấu hình giám sát.
- Lấy thống kê hiện tại hoặc lịch sử nếu có lưu trữ.
- Bắt đầu/dừng packet capture.
- Thay đổi interface được giám sát.
- Cập nhật ngưỡng cảnh báo.

Các endpoint dự kiến (có thể thay đổi khi thiết kế API):

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/health` | Kiểm tra tình trạng Server |
| GET | `/api/system` | Thông tin hệ thống |
| GET | `/api/interfaces` | Danh sách giao diện mạng |
| GET | `/api/monitor/status` | Trạng thái giám sát |
| GET | `/api/monitor/config` | Lấy cấu hình |
| PUT | `/api/monitor/config` | Cập nhật cấu hình |
| POST | `/api/capture/start` | Bắt đầu capture |
| POST | `/api/capture/stop` | Dừng capture |
| GET | `/api/statistics/current` | Lấy thống kê hiện tại |

Đây là API đề xuất, không được coi là endpoint đã tồn tại trước khi kiểm tra source code.

### 3.2. WebSocket

Sử dụng WebSocket cho luồng dữ liệu hai chiều, duy trì kết nối lâu dài giữa Client và Server.

Dữ liệu Server có thể đẩy định kỳ:

- Timestamp.
- Interface đang giám sát.
- Upload/download bytes per second.
- Tổng bytes gửi/nhận.
- Số packet.
- Thống kê giao thức.
- Top Talkers/flows.
- Trạng thái capture.
- Cảnh báo.

Đường dẫn dự kiến: `/ws`.

Định dạng message đã triển khai (Giai đoạn 4): mọi message có lớp bao gồm `type`, `timestamp` (UTC, hậu tố `Z`) và `data`. Ví dụ `traffic_update`:

```json
{
  "type": "traffic_update",
  "timestamp": "2026-01-01T10:30:00Z",
  "data": {
    "interface": "Ethernet",
    "upload_bytes_per_second": 125000.0,
    "download_bytes_per_second": 850000.0,
    "total_sent_bytes": 1024000,
    "total_received_bytes": 8192000,
    "total_sent_packets": 10000,
    "total_received_packets": 80000
  }
}
```

Các loại message dự kiến:

- `traffic_update`: cập nhật lưu lượng (đã triển khai).
- `protocol_update`: cập nhật thống kê giao thức.
- `flow_update`: cập nhật Top Talkers.
- `alert`: cảnh báo.
- `capture_status`: trạng thái packet capture.
- `server_status`: trạng thái Server (đã triển khai: gửi khi kết nối và khi trạng thái đổi giữa `ok` và `degraded`).
- `error`: thông báo lỗi (đã triển khai cho message sai từ Client).
- `ping` / `pong`: kiểm tra kết nối nếu cần (đã triển khai: Client gửi `ping`, Server trả `pong`).

Cần thiết kế rõ cấu trúc message, kiểu dữ liệu, đơn vị đo và tần suất gửi. Không gửi dữ liệu packet quá lớn hoặc không cần thiết qua WebSocket.

### 3.3. Vì sao dùng cả HTTP và WebSocket?

- HTTP phù hợp với thao tác yêu cầu – phản hồi, truy vấn cấu hình và điều khiển.
- WebSocket phù hợp với dữ liệu thay đổi liên tục, giúp Server chủ động đẩy dữ liệu đến Client mà không cần Client liên tục polling HTTP.
- Hai giao thức bổ sung cho nhau, không thay thế nhau.

### 3.4. TCP/IP và bảo mật truyền thông

HTTP và WebSocket thông thường chạy trên TCP. Khi triển khai thực tế ngoài môi trường lab, cần cân nhắc HTTPS/WSS, xác thực Client, giới hạn quyền điều khiển, kiểm tra dữ liệu đầu vào và giới hạn tốc độ gửi message.

Không hard-code mật khẩu, token hoặc API key trong source code. Không ghi token hoặc dữ liệu nhạy cảm vào log.

---

## 4. Công nghệ và thư viện Python dự kiến

Chỉ sử dụng thư viện thật sự cần thiết. Kiểm tra khả năng tương thích phiên bản Python và hệ điều hành trước khi cài đặt.

| Thành phần | Công nghệ dự kiến | Vai trò |
|---|---|---|
| Ngôn ngữ | Python 3.10+ | Ngôn ngữ chính |
| Server API | FastAPI | Xây dựng HTTP API và WebSocket |
| ASGI Server | Uvicorn | Chạy FastAPI |
| Client GUI | PyQt6 | Giao diện máy Guest |
| Server GUI | PyQt6 | Giao diện quản trị trên Host |
| Biểu đồ | pyqtgraph | Biểu đồ lưu lượng thời gian thực |
| Network counters | psutil | Đọc thống kê interface |
| Packet capture | Scapy | Phân tích packet metadata khi được cấp quyền |
| Packet capture driver (Windows) | Npcap | Hỗ trợ capture trên Windows |
| HTTP Client | httpx hoặc requests | Gọi HTTP API |
| WebSocket Client | websockets hoặc thư viện phù hợp | Nhận dữ liệu realtime |
| Logging | logging | Ghi log |
| Cấu hình | JSON hoặc Pydantic Settings | Quản lý cấu hình |
| Kiểm thử | pytest | Kiểm thử đơn vị và tích hợp |

Không cài đặt tất cả thư viện một cách máy móc. Trước khi thêm dependency, giải thích lý do và kiểm tra xem thư viện hiện có đã đáp ứng chưa.

### 4.1. Phân biệt thống kê và packet capture

- `psutil` cung cấp bộ đếm byte/packet theo interface; phù hợp để tính tốc độ upload/download tổng thể.
- `Scapy`/Npcap phục vụ capture và phân tích metadata packet; có thể cần quyền Administrator trên Windows hoặc root/capabilities trên Linux.
- Packet capture có thể không hoạt động trên một số interface, driver hoặc môi trường máy ảo. Cần hiển thị lỗi và trạng thái rõ ràng.
- Không suy luận rằng một packet là HTTP chỉ vì nó dùng TCP. HTTPS mã hóa payload; chỉ phân loại giao thức ở mức có thể quan sát được.
- Không thu thập hoặc lưu payload nhạy cảm nếu không cần thiết. Ưu tiên metadata như timestamp, source/destination IP, port, protocol, packet length và direction.

---

## 5. Chức năng và giao diện

### 5.1. Client GUI – Guest

Giao diện Client tập trung vào trải nghiệm giám sát:

- Khu vực cấu hình Server IP/Port và nút Connect/Disconnect.
- Trạng thái kết nối HTTP và WebSocket.
- Chọn interface được giám sát.
- Biểu đồ upload/download theo thời gian thực.
- Thống kê tổng gửi/nhận.
- Thống kê giao thức.
- Top Talkers theo source/destination.
- Danh sách packet metadata (nếu tính năng capture được bật).
- Khu vực cảnh báo khi vượt ngưỡng.
- Thời gian cập nhật dữ liệu gần nhất.

Có thể tổ chức thành các tab:
1. **Biểu đồ băng thông thời gian thực**
2. **Phân tích giao thức và Top Talkers**
3. **Packet Details** (nếu khối lượng chức năng và yêu cầu bài tập phù hợp)

Không tự ý xóa hoặc thay đổi bố cục lớn khi người dùng chưa yêu cầu.

### 5.2. Server GUI – Host

Giao diện Server phục vụ quản trị và theo dõi hoạt động:

- Nút Start/Stop Server hoặc hiển thị trạng thái tiến trình.
- Địa chỉ IP và port đang lắng nghe.
- Danh sách network interfaces trên Host.
- Interface đang được thu thập.
- Trạng thái collector và packet capture.
- Danh sách Client đang kết nối, thời điểm kết nối và trạng thái WebSocket.
- Thống kê tổng quan upload/download.
- Cấu hình chu kỳ cập nhật và ngưỡng cảnh báo.
- Nhật ký hoạt động, lỗi và cảnh báo.

Server GUI phải không làm treo tiến trình thu thập dữ liệu. Công việc blocking hoặc I/O cần chạy trong worker/thread/async task thích hợp.

### 5.3. Quy tắc cập nhật giao diện

- Không cập nhật widget Qt trực tiếp từ thread nền.
- Dùng Qt Signals/Slots hoặc cơ chế thread-safe phù hợp để chuyển dữ liệu về GUI thread.
- Không chạy vòng lặp vô hạn hoặc thao tác blocking trong GUI thread.
- Khi mất WebSocket, hiển thị trạng thái và thử kết nối lại có kiểm soát.
- Dữ liệu cũ phải được đánh dấu hoặc loại bỏ hợp lý, tránh hiển thị như dữ liệu mới.

---

## 6. Kiến trúc phần mềm và phân chia module

Thiết kế theo hướng tách biệt trách nhiệm:

1. **Core/Collector:** Thu thập thống kê interface.
2. **Core/Sniffer:** Packet capture và phân tích metadata.
3. **Server/API:** HTTP routes, WebSocket endpoint, quản lý Client.
4. **Server/Service:** Điều phối collector, sniffer, thống kê và cảnh báo.
5. **Client/Network:** HTTP client, WebSocket client, xử lý reconnect.
6. **Client/GUI:** Giao diện giám sát trên Guest.
7. **Server GUI:** Giao diện quản trị trên Host.
8. **Models/Schemas:** Cấu trúc dữ liệu và validation.
9. **Config:** Cấu hình tập trung.
10. **Tests:** Kiểm thử các thành phần.

### 6.1. Cấu trúc thư mục tham khảo

Đây là cấu trúc gợi ý. Có thể điều chỉnh khi có lý do kỹ thuật, nhưng cần giữ nhất quán và cập nhật tài liệu.

```text
networking-traffic-monitor/
├── main.py
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── network_monitor/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── collector.py
│   │   ├── sniffer.py
│   │   ├── traffic_analyzer.py
│   │   └── alert_manager.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   │
│   ├── server/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── routes.py
│   │   ├── websocket_manager.py
│   │   └── monitoring_service.py
│   │
│   ├── client/
│   │   ├── __init__.py
│   │   ├── api_client.py
│   │   ├── websocket_client.py
│   │   └── connection_manager.py
│   │
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── client/
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py
│   │   │   └── widgets/
│   │   └── server/
│   │       ├── __init__.py
│   │       ├── server_window.py
│   │       └── widgets/
│   │
│   └── utils/
│       ├── __init__.py
│       └── logger.py
│
├── tests/
│   ├── test_collector.py
│   ├── test_api.py
│   └── test_websocket.py
│
└── data/
    └── logs/
```

### 6.2. Quy tắc import và chạy chương trình

- Ưu tiên absolute imports nhất quán, ví dụ `from network_monitor.core.collector import NetworkCollector`.
- Không tự ý trộn nhiều kiểu import gây lỗi khi chạy từ thư mục gốc.
- Có entry point rõ ràng để chạy Server và Client.
- Ví dụ lệnh dự kiến:

```powershell
# Chạy Server trên Host
python main.py server

# Chạy Client GUI trên Guest
python main.py client
```

Các lệnh trên là giao diện dòng lệnh dự kiến. Chỉ sử dụng sau khi đã triển khai entry point tương ứng.

---

## 7. Luồng hoạt động chính

### 7.1. Khởi động Server

1. Người dùng mở Server GUI trên Host.
2. Server GUI khởi tạo cấu hình.
3. FastAPI/Uvicorn khởi chạy trên địa chỉ và port đã cấu hình.
4. Collector phát hiện interface và bắt đầu lấy counters theo chu kỳ.
5. Sniffer chỉ bắt đầu khi được bật và có đủ quyền.
6. Server cập nhật trạng thái và sẵn sàng nhận Client.

### 7.2. Client kết nối

1. Người dùng mở Client GUI trên Guest.
2. Nhập hoặc chọn địa chỉ Server.
3. Client gọi HTTP health check.
4. Nếu Server khả dụng, Client lấy danh sách interface/cấu hình.
5. Client mở WebSocket.
6. Server xác nhận kết nối và gửi dữ liệu theo chu kỳ.
7. Client cập nhật biểu đồ và các bảng thống kê.

### 7.3. Cảnh báo

1. Server tính tốc độ lưu lượng theo đơn vị đã thống nhất.
2. So sánh với ngưỡng cấu hình.
3. Nếu vượt ngưỡng, Server phát sinh alert event.
4. Server GUI và Client GUI hiển thị cảnh báo phù hợp.
5. Tránh phát cảnh báo lặp liên tục; cần có cooldown hoặc cơ chế xác định trạng thái cảnh báo.

### 7.4. Mất kết nối

1. Client phát hiện WebSocket đóng hoặc timeout.
2. Hiển thị trạng thái mất kết nối.
3. Thử reconnect với backoff và giới hạn số lần/tần suất phù hợp.
4. Sau khi kết nối lại, đồng bộ lại trạng thái qua HTTP.
5. Không giả mạo dữ liệu realtime trong thời gian mất kết nối.

---

## 8. Quy ước dữ liệu và đơn vị

Phải thống nhất đơn vị giữa Server, WebSocket, Client và giao diện:

- Byte: đơn vị dữ liệu nền.
- B/s: byte mỗi giây.
- bit/s: bit mỗi giây; quy đổi `1 byte = 8 bits`.
- Có thể hiển thị KB/s, MB/s hoặc Mbps nhưng phải ghi rõ quy ước hệ số 1000 hay 1024.
- Timestamp nên có timezone rõ ràng, ưu tiên ISO 8601.
- IP, port, protocol, direction và interface phải có tên trường thống nhất.

Không dùng lẫn lộn `bytes_per_second`, `bits_per_second`, `upload_speed` nếu chưa định nghĩa rõ.

Mỗi message WebSocket nên có trường `type`, `timestamp` và `data` hoặc một schema thống nhất đã được tài liệu hóa.

---

## 9. Yêu cầu chất lượng, an toàn và độ tin cậy

- Chỉ capture trên interface mà người vận hành được phép giám sát.
- Thông báo rõ nếu thiếu quyền Administrator/root hoặc thiếu Npcap.
- Không lưu payload nhạy cảm nếu không cần thiết.
- Không hard-code secret.
- Validate dữ liệu đầu vào từ Client.
- Xử lý ngoại lệ ở ranh giới I/O và ghi log đủ thông tin nhưng không lộ secret.
- Không để lỗi một Client làm dừng Server hoặc ảnh hưởng Client khác.
- Quản lý vòng đời thread/task/socket rõ ràng.
- Đóng WebSocket, sniffer, collector và worker khi thoát ứng dụng.
- Giới hạn kích thước message, tần suất gửi và số packet lưu trong bộ nhớ.
- Tách cấu hình khỏi source code.
- Không tuyên bố hệ thống an toàn tuyệt đối; mô tả đúng các biện pháp đã triển khai.

---

## 10. Kiểm thử và tiêu chí nghiệm thu

Mỗi chức năng cần có cách kiểm thử cụ thể.

| Nhóm | Nội dung kiểm thử | Kết quả mong đợi |
|---|---|---|
| Server | Khởi động/dừng | Server khởi động và dừng có kiểm soát |
| HTTP | Health check | Client nhận trạng thái Server |
| HTTP | Lấy danh sách interface | Trả về danh sách interface hợp lệ |
| WebSocket | Kết nối từ Guest | Kết nối được qua Host-only Network |
| WebSocket | Dữ liệu realtime | Client nhận message định kỳ |
| Collector | Upload/download | Counter và tốc độ được cập nhật |
| Sniffer | Capture packet | Có dữ liệu khi đủ quyền và driver |
| Protocol | Phân loại | Thống kê khớp với dữ liệu quan sát được |
| Alert | Vượt ngưỡng | Server và Client nhận cảnh báo |
| Reconnect | Ngắt kết nối | Client báo mất kết nối và phục hồi |
| GUI | Cập nhật | Không treo hoặc crash khi cập nhật |
| Multi-client | Nhiều Client | Một Client lỗi không làm dừng các Client khác |

Cần phân biệt:
- Unit test: kiểm tra module riêng.
- Integration test: kiểm tra API, collector, WebSocket phối hợp.
- System test: kiểm tra Host–Guest qua VirtualBox.
- Manual test: kiểm tra giao diện và tình huống thực tế.

Không đánh dấu tiêu chí là đạt nếu chưa có bằng chứng chạy thử hoặc test tương ứng.

---

## 11. Kế hoạch phát triển đề xuất

Thực hiện theo từng giai đoạn nhỏ, chạy được và kiểm thử được:

1. Khảo sát môi trường, xác nhận Python, hệ điều hành, VirtualBox và mạng Host-only.
2. Tạo cấu trúc thư mục, virtual environment và dependency tối thiểu.
3. Viết Collector dùng psutil và kiểm thử trên Host.
4. Xây dựng FastAPI HTTP API.
5. Xây dựng WebSocket và kiểm thử bằng công cụ đơn giản trước khi làm GUI.
6. Xây dựng Client GUI trên Guest, tích hợp HTTP và WebSocket.
7. Xây dựng Server GUI trên Host.
8. Tích hợp packet capture và phân tích metadata.
9. Hoàn thiện protocol statistics, Top Talkers và alert.
10. Kiểm thử toàn hệ thống, xử lý lỗi và viết tài liệu báo cáo.

Không triển khai tất cả chức năng cùng lúc. Ưu tiên tạo một luồng end-to-end tối thiểu: Host thu thập counters → Server phát WebSocket → Guest nhận và hiển thị.

---

## 12. Quy tắc làm việc dành cho Claude

Đây là các quy tắc bắt buộc khi hỗ trợ dự án.

### 12.1. Trước khi chỉnh sửa

1. Đọc file `CLAUDE.md` này.
2. Kiểm tra cấu trúc thư mục và source code hiện tại.
3. Xác định chức năng nào đã có, chức năng nào chưa có.
4. Đọc các file liên quan trước khi sửa.
5. Nêu ngắn gọn nguyên nhân và kế hoạch sửa nếu thay đổi ảnh hưởng nhiều module.
6. Không giả định cấu trúc, class, function, endpoint hoặc biến đã tồn tại nếu chưa kiểm tra.

### 12.2. Khi viết code

- Dùng Python theo phiên bản đã xác nhận trong môi trường dự án.
- Tên biến, hàm, class và module dùng tiếng Anh.
- Nội dung giao diện, thông báo và log hiển thị cho người dùng ưu tiên tiếng Việt.
- Viết code rõ ràng, có type hints khi phù hợp.
- Tách biệt GUI, business logic, network communication và data collection.
- Không đặt toàn bộ dự án vào một file lớn.
- Không tạo file trùng chức năng.
- Không tự ý thay framework hoặc kiến trúc đã thống nhất.
- Không tự ý xóa chức năng đang hoạt động.
- Không dùng dữ liệu giả để làm giao diện trông như đang chạy thật, trừ khi ghi nhãn rõ là demo/mock.
- Không để GUI thread thực hiện network I/O hoặc packet capture blocking.

### 12.3. Khi sửa lỗi

- Giải thích lỗi đến từ đâu.
- Chỉ ra file và vị trí cần thay đổi.
- Đưa ra nội dung hoàn chỉnh của file khi người dùng yêu cầu full file.
- Giữ tương thích với các module đang gọi file/hàm đó.
- Sau khi sửa, đưa lệnh chạy và cách kiểm thử.
- Nếu chưa thể xác minh bằng cách chạy code, nói rõ chưa được kiểm thử.

### 12.4. Cách trả lời

- Trả lời bằng tiếng Việt.
- Hướng dẫn từng bước, theo đúng thứ tự thực hiện.
- Khi cần tạo code, ghi rõ đường dẫn file.
- Nếu yêu cầu nhiều file, liệt kê cấu trúc trước rồi cung cấp từng file.
- Không bỏ qua bước cài đặt, cấu hình hoặc chạy thử cần thiết.
- Giải thích ngắn gọn lý do chọn giải pháp.
- Không đưa ra quá nhiều lựa chọn nếu có một phương án phù hợp rõ ràng.
- Khi thiếu thông tin quan trọng, hỏi một câu cụ thể thay vì tự đoán.

### 12.5. Quản lý tài liệu

Khi kiến trúc, endpoint, cấu trúc thư mục hoặc quyết định kỹ thuật thay đổi:
- Cập nhật `CLAUDE.md` nếu thay đổi ảnh hưởng định hướng chung.
- Cập nhật `README.md` cho hướng dẫn cài đặt/chạy dự án.
- Cập nhật tài liệu API/schema khi thay đổi giao tiếp Client–Server.
- Không ghi trạng thái “đã hoàn thành” khi mới chỉ đề xuất hoặc tạo code nhưng chưa kiểm thử.

---

## 13. Những điều Claude không được tự giả định

1. Không giả định Host-only IP luôn là `192.168.56.1`.
2. Không giả định Guest luôn dùng Windows; cần xác nhận hệ điều hành Guest.
3. Không giả định Npcap đã được cài hoặc packet capture đã hoạt động.
4. Không giả định mọi interface đều hỗ trợ capture.
5. Không giả định HTTPS payload có thể đọc được.
6. Không giả định HTTP API hoặc WebSocket endpoint đã tồn tại chỉ vì được đề xuất trong tài liệu.
7. Không giả định Server GUI và FastAPI Server là cùng một thành phần.
8. Không giả định Client có quyền đọc trực tiếp file hoặc dữ liệu trên Host.
9. Không giả định code đã chạy thành công nếu chưa có kết quả kiểm thử.
10. Không tự ý đổi tên thư mục, package, entry point hoặc giao thức mà không giải thích và được người dùng đồng ý khi thay đổi có ảnh hưởng lớn.

---

## 14. Thông tin cần xác nhận khi bắt đầu triển khai

Nếu chưa có trong source code hoặc trao đổi trước đó, hãy hỏi người dùng những thông tin thực sự cần thiết, chẳng hạn:

- Hệ điều hành Host và Guest.
- Phiên bản Python.
- IDE sử dụng.
- Phiên bản VirtualBox.
- Mạng VM đang dùng: Host-only, Bridged hay NAT.
- Địa chỉ IP Host-only thực tế.
- Yêu cầu cụ thể của giảng viên về giao thức và chức năng.
- Có bắt buộc packet capture hay chỉ cần thống kê interface.
- Có yêu cầu lưu lịch sử vào database hay không.

Không cần hỏi lại thông tin đã được cung cấp hoặc có thể xác minh trực tiếp từ project.

---

## 15. Trạng thái triển khai

Cập nhật mục này trong quá trình phát triển:

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Phân tích yêu cầu | Đã thực hiện | Đã đọc CLAUDE.md và thống nhất lộ trình 10 giai đoạn với người dùng |
| Thiết kế kiến trúc | Định hướng ban đầu | Đã hoàn thiện kiến trúc Client-Server đa luồng |
| Python environment | Đã xác nhận (Host) | Host: Windows 11 Home build 26200, Python 3.13.2, RAM 15.3 GB. `.venv` đã cài đủ `PyQt6`, `pyqtgraph`, `numpy`, `scapy` |
| Khung dự án (Giai đoạn 1) | Đã thực hiện | Cấu trúc thư mục, `main.py` (CLI), `requirements.txt`. Đã kiểm chứng |
| Network Collector (Giai đoạn 2) | Đã triển khai | `core/collector.py`. Đã kiểm thử trên Host, đối chiếu Task Manager |
| HTTP API (Giai đoạn 3) | Đã triển khai | `server/routes.py`, `server/monitoring_service.py`. 40/40 pytest PASSED |
| WebSocket (Giai đoạn 4) | Đã triển khai | `server/websocket_manager.py`, endpoint `/ws`. 68/68 pytest PASSED |
| Client GUI (Giai đoạn 5) | Đã triển khai | `gui/client/main_window.py`. PyQt6 + pyqtgraph realtime traffic plot. Đã kiểm chứng |
| Reconnect & Resync (Giai đoạn 6) | Đã triển khai | WebSocket reconnect backoff, chèn `np.nan` ngắt nét vẽ khi rớt mạng, tự gọi HTTP REST resync trạng thái/interface khi phục hồi. Đã kiểm chứng |
| Server GUI (Giai đoạn 7) | Đã triển khai | `gui/server/server_window.py`, `server_thread.py`. Quản trị Server bằng PyQt6 trên Host, điều khiển Uvicorn trong QThread phụ, chuyển hướng Python logging về GUI console |
| Packet Sniffer (Giai đoạn 8) | Đã triển khai | `core/sniffer.py`, các HTTP REST endpoints `/api/capture/*`. Tích hợp Scapy/Npcap trích xuất metadata gói tin qua Ring Buffer |
| Protocol / Top Talkers / Alert (Giai đoạn 9) | Đã triển khai | `core/analyzer.py`, `core/alert_engine.py`, các endpoints `/api/analytics/*` & `/api/alerts/*` |
| Integration Testing (Giai đoạn 10) | Đã triển khai | `tests/test_integration.py`, `README.md`. Kiểm thử End-to-End toàn hệ thống và đóng gói dự án. 74/74 pytest PASSED |

**Kiểm thử bản cập nhật (Giai đoạn 10):**
- Đã chạy thành công 74/74 unit & integration tests trong pytest suite (`test_integration.py` đạt 100%).
- Đã kiểm tra giải phóng tài nguyên: Khi đóng ứng dụng Server GUI và Client GUI, toàn bộ `QThread`, `asyncio` task và `threading.Thread` của Scapy được dừng hoàn toàn, không có tài nguyên rò rỉ hay tiến trình chạy ẩn.
- Đã hoàn thiện tài liệu hướng dẫn vận hành chi tiết tại `README.md`.

**Giới hạn đã biết:**
- API và WebSocket hiện tại chưa tích hợp xác thực; Server mặc định bind vào `127.0.0.1`.
- Tính năng Packet Capture (Giai đoạn 8) yêu cầu Npcap và ứng dụng phải chạy dưới quyền Administrator trên Windows.
- Ngưỡng cảnh báo `AlertRule` mặc định kiểm tra trên đơn vị Byte/giây; nếu đặt ngưỡng = 0 thì mọi lưu lượng > 0 B/s đều sẽ kích hoạt cảnh báo.
- Bộ nhớ đệm Ring Buffer của Packet Capture mặc định lưu trữ 1000 gói tin gần nhất để tối ưu bộ nhớ RAM.

**Nguyên tắc cập nhật:** Chỉ đổi trạng thái sau khi có bằng chứng tương ứng. Ghi rõ lỗi, giới hạn và phần còn thiếu.
