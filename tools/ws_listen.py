"""Công cụ dòng lệnh ĐỘC LẬP để xem message WebSocket của Network Monitor.

Chỉ cần thư viện ``websockets`` (đã cài cùng ``uvicorn[standard]``), không import gì từ dự án,
nên có thể chép riêng sang máy Guest để thử kết nối trước khi có Client GUI.

Ví dụ:
    python tools/ws_listen.py
    python tools/ws_listen.py --url ws://192.168.56.1:8000/ws --count 10
    python tools/ws_listen.py --raw --ping-interval 5
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Any

try:
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed, WebSocketException
except ImportError:
    print("Thiếu thư viện 'websockets'. Cài bằng: pip install websockets", file=sys.stderr)
    sys.exit(1)

DEFAULT_URL = "ws://127.0.0.1:8000/ws"


def _scale(value: float, units: tuple[str, ...]) -> str:
    """Quy đổi theo hệ số 1000, giống lệnh `collect` của dự án."""
    for unit in units[:-1]:
        if abs(value) < 1000:
            return f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} {units[-1]}"


def _format_rate(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    return f"{_scale(value, ('B/s', 'KB/s', 'MB/s', 'GB/s'))} ({value * 8 / 1_000_000:.2f} Mbps)"


def _format_size(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    return _scale(value, ("B", "KB", "MB", "GB", "TB"))


def _clock(timestamp: Any) -> str:
    try:
        moment = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        return moment.astimezone().strftime("%H:%M:%S")
    except ValueError:
        return "--:--:--"


def describe(text: str) -> str:
    """Biến một message JSON thành một dòng dễ đọc."""
    try:
        message = json.loads(text)
    except ValueError:
        return f"(không phải JSON) {text}"
    if not isinstance(message, dict):
        return text
    kind = message.get("type")
    data = message.get("data")
    if not isinstance(data, dict):
        data = {}
    prefix = f"[{_clock(message.get('timestamp'))}] {kind}"
    if kind == "traffic_update":
        return (
            f"{prefix} | {data.get('interface')} | "
            f"Gửi: {_format_rate(data.get('upload_bytes_per_second'))} | "
            f"Nhận: {_format_rate(data.get('download_bytes_per_second'))} | "
            f"Tổng gửi: {_format_size(data.get('total_sent_bytes'))} | "
            f"Tổng nhận: {_format_size(data.get('total_received_bytes'))}"
        )
    if kind == "server_status":
        return (
            f"{prefix} | trạng thái: {data.get('status')} | interface: {data.get('monitored_interface')} | "
            f"chu kỳ: {data.get('sample_interval_seconds')}s | lỗi: {data.get('last_error') or '-'}"
        )
    if kind == "error":
        return f"{prefix} | {data.get('code')}: {data.get('message')}"
    return f"{prefix} | {text}"


async def _ping_loop(websocket: Any, interval: float) -> None:
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send(json.dumps({"type": "ping"}))
    except ConnectionClosed:
        return


async def listen(url: str, count: int, raw: bool, ping_interval: float) -> int:
    try:
        async with connect(url) as websocket:
            print(f"Đã kết nối tới {url}. Nhấn Ctrl+C để dừng.")
            pinger = (
                asyncio.create_task(_ping_loop(websocket, ping_interval))
                if ping_interval > 0
                else None
            )
            received = 0
            try:
                async for text in websocket:
                    print(text if raw else describe(str(text)))
                    received += 1
                    if count and received >= count:
                        print(f"Đã nhận đủ {count} message, dừng.")
                        return 0
            finally:
                if pinger is not None:
                    pinger.cancel()
            print(
                f"Server đã đóng kết nối (mã {websocket.close_code}, "
                f"lý do: {websocket.close_reason or '-'})."
            )
            return 0
    except ConnectionClosed as exc:
        print(f"Mất kết nối: {exc}", file=sys.stderr)
        return 1
    except (OSError, WebSocketException) as exc:
        print(f"Không kết nối được tới {url}: {exc}", file=sys.stderr)
        return 1


def _positive_float(text: str) -> float:
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError("giá trị không được âm")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Xem message WebSocket của Network Monitor.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"URL WebSocket (mặc định {DEFAULT_URL})")
    parser.add_argument("--count", type=int, default=0, help="Dừng sau N message (0 = không giới hạn)")
    parser.add_argument("--raw", action="store_true", help="In JSON gốc thay vì dòng rút gọn")
    parser.add_argument(
        "--ping-interval",
        type=_positive_float,
        default=0.0,
        help="Gửi ping mỗi N giây (0 = không gửi)",
    )
    args = parser.parse_args(argv)
    try:
        return asyncio.run(listen(args.url, args.count, args.raw, args.ping_interval))
    except KeyboardInterrupt:
        print("\nĐã dừng.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
