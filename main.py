"""Entry point của Network Monitor.

Cách chạy (từ thư mục gốc dự án):
    python main.py server     # Chạy HTTP API trên Host (chưa có Server GUI)
    python main.py client     # Chạy Client GUI trên Guest (chưa triển khai)
    python main.py collect    # Chẩn đoán: in lưu lượng thật của một interface (Giai đoạn 2)
"""

import argparse
import dataclasses
import sys
import time
from collections.abc import Sequence

from network_monitor import __version__

MIN_PYTHON = (3, 10)
SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")
RATE_UNITS = ("B/s", "KB/s", "MB/s", "GB/s")


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' không phải số hợp lệ") from None
    if value <= 0:
        raise argparse.ArgumentTypeError("giá trị phải lớn hơn 0")
    return value


def _non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' không phải số nguyên hợp lệ") from None
    if value < 0:
        raise argparse.ArgumentTypeError("giá trị không được âm")
    return value


def _port(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' không phải số nguyên hợp lệ") from None
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError("port phải nằm trong khoảng 1-65535")
    return value


def _scale(value: float, units: Sequence[str]) -> str:
    """Quy đổi theo hệ số 1000 (CLAUDE.md mục 8)."""
    for unit in units[:-1]:
        if abs(value) < 1000:
            return f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} {units[-1]}"


def _format_rate(bytes_per_second: float | None) -> str:
    if bytes_per_second is None:
        return "chưa đo"
    megabits_per_second = bytes_per_second * 8 / 1_000_000
    return f"{_scale(bytes_per_second, RATE_UNITS)} ({megabits_per_second:.2f} Mbps)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Network Monitor - giám sát lưu lượng mạng bằng HTTP và WebSocket.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="{server,client,collect}")
    subparsers.required = True
    server = subparsers.add_parser("server", help="Chạy HTTP API trên Host (chưa có Server GUI)")
    server.add_argument("--host", help="Địa chỉ lắng nghe (mặc định 127.0.0.1)")
    server.add_argument("--port", type=_port, help="Cổng lắng nghe (mặc định 8000)")
    server.add_argument("-i", "--interface", help="Interface cần giám sát (mặc định: tự chọn)")
    subparsers.add_parser("client", help="Chạy Client GUI trên Guest (chưa triển khai)")

    collect = subparsers.add_parser(
        "collect", help="Chẩn đoán: in lưu lượng thật của một interface trên máy này"
    )
    collect.add_argument("-i", "--interface", help="Tên interface (mặc định: tự chọn)")
    collect.add_argument(
        "--interval", type=_positive_float, default=1.0, help="Chu kỳ lấy mẫu, giây (mặc định 1.0)"
    )
    collect.add_argument(
        "--count",
        type=_non_negative_int,
        default=0,
        help="Số mẫu cần in rồi dừng (mặc định 0 = chạy đến khi nhấn Ctrl+C)",
    )
    collect.add_argument("--list", action="store_true", help="Chỉ liệt kê interface rồi thoát")
    collect.add_argument(
        "--all", action="store_true", help="Với --list: gồm cả interface ngắt kết nối và loopback"
    )
    return parser


def _run_collect(args: argparse.Namespace) -> int:
    try:
        from network_monitor.core.collector import InterfaceNotFoundError, NetworkCollector
    except ImportError as exc:
        print(f"Thiếu thư viện: {exc}. Hãy chạy: pip install -r requirements.txt", file=sys.stderr)
        return 1

    collector = NetworkCollector()

    if args.list:
        interfaces = collector.list_interfaces(include_all=args.all)
        if not interfaces:
            print("Không có interface nào phù hợp (thử thêm --all).")
            return 0
        for info in interfaces:
            state = "UP" if info.is_up else "DOWN"
            speed = f"{info.speed_mbps} Mbps" if info.speed_mbps else "không rõ"
            addresses = ", ".join(info.ipv4_addresses) or "-"
            print(f"- {info.name} | {state} | tốc độ liên kết: {speed} | IPv4: {addresses}")
        return 0

    name = args.interface or collector.default_interface()
    if name is None:
        print(
            "Không tìm thấy interface đang hoạt động. "
            "Dùng 'collect --list --all' để xem, hoặc chỉ định --interface.",
            file=sys.stderr,
        )
        return 1

    try:
        collector.sample(name)  # Lấy mốc so sánh ban đầu, không in
    except InterfaceNotFoundError as exc:
        print(exc, file=sys.stderr)
        available = ", ".join(i.name for i in collector.list_interfaces(include_all=True))
        print(f"Các interface hiện có: {available}", file=sys.stderr)
        return 1

    print(f"Đang giám sát interface: {name} (chu kỳ {args.interval}s). Nhấn Ctrl+C để dừng.")
    printed = 0
    try:
        while args.count == 0 or printed < args.count:
            time.sleep(args.interval)
            sample = collector.sample(name)
            clock = sample.timestamp.astimezone().strftime("%H:%M:%S")
            print(
                f"[{clock}] {sample.interface} | "
                f"Gửi: {_format_rate(sample.upload_bytes_per_second)} | "
                f"Nhận: {_format_rate(sample.download_bytes_per_second)} | "
                f"Tổng gửi: {_scale(sample.total_sent_bytes, SIZE_UNITS)} | "
                f"Tổng nhận: {_scale(sample.total_received_bytes, SIZE_UNITS)}"
            )
            printed += 1
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    return 0


def _run_server(args: argparse.Namespace) -> int:
    try:
        from network_monitor.config import Settings
        from network_monitor.server.main import run_server
    except ImportError as exc:
        print(f"Thiếu thư viện: {exc}. Hãy chạy: pip install -r requirements.txt", file=sys.stderr)
        return 1

    try:
        settings = Settings.from_env()
        overrides = {
            key: value
            for key, value in (
                ("host", args.host),
                ("port", args.port),
                ("interface", args.interface),
            )
            if value is not None
        }
        settings = dataclasses.replace(settings, **overrides)
    except ValueError as exc:
        print(f"Cấu hình không hợp lệ: {exc}", file=sys.stderr)
        return 1

    print(f"Khởi động Server tại http://{settings.host}:{settings.port} (tài liệu API: /docs)")
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Cảnh báo: API chưa có xác thực và đang mở ngoài máy này. "
            "Chỉ dùng trong mạng lab, không mở ra Internet."
        )
    print("Nhấn Ctrl+C để dừng.")
    run_server(settings)
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(n) for n in MIN_PYTHON)
        print(f"Cần Python {required} trở lên.", file=sys.stderr)
        return 1

    args = build_parser().parse_args(argv)
    if args.command == "collect":
        return _run_collect(args)
    if args.command == "server":
        return _run_server(args)
    # Các giai đoạn sau sẽ thay thế thông báo này bằng logic thật.
    print(f"Lệnh '{args.command}' chưa được triển khai (Giai đoạn 4: mới có Collector, HTTP API và WebSocket).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
