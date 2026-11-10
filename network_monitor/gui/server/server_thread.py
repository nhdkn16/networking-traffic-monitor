import logging
import uvicorn
from PyQt6.QtCore import QThread, pyqtSignal
from network_monitor.config import Settings
from network_monitor.server.main import create_app

logger = logging.getLogger(__name__)

class QtLogHandler(logging.Handler):
    """Custom LogHandler chuyển hướng log của Python logging về PyQt Signal."""

    def __init__(self, signal: pyqtSignal):
        super().__init__()
        self.signal = signal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.signal.emit(msg)
        except Exception:
            self.handleError(record)

class ServerWorkerThread(QThread):
    """QThread điều hành Uvicorn ASGI Server chạy độc lập với GUI thread."""

    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)  # status_code, message

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.server: uvicorn.Server | None = None
        self._handler: QtLogHandler | None = None

    def run(self) -> None:
        app = create_app(self.settings)

        config = uvicorn.Config(
            app=app,
            host=self.settings.host,
            port=self.settings.port,
            log_level="info",
            loop="asyncio",
        )
        self.server = uvicorn.Server(config)

        self._handler = QtLogHandler(self.log_signal)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        self._handler.setFormatter(formatter)
        logging.getLogger("network_monitor").addHandler(self._handler)
        logging.getLogger("uvicorn").addHandler(self._handler)

        self.status_signal.emit("running", f"Server đang chạy tại http://{self.settings.host}:{self.settings.port}")

        try:
            self.server.run()
        except Exception as exc:
            self.status_signal.emit("error", f"Lỗi Server: {exc}")
        finally:
            if self._handler:
                logging.getLogger("network_monitor").removeHandler(self._handler)
                logging.getLogger("uvicorn").removeHandler(self._handler)
            self.status_signal.emit("stopped", "Server đã dừng.")

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
            