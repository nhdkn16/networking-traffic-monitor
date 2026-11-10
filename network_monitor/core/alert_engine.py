"""Module AlertEngine: Quản lý quy tắc và phát sinh sự kiện cảnh báo băng thông."""

import collections
from datetime import datetime, timezone

from network_monitor.models.schemas import AlertEvent, AlertRule, TrafficSample


class AlertEngine:
    """Động cơ so sánh ngưỡng lưu lượng và lưu giữ lịch sử cảnh báo."""

    def __init__(self, rule: AlertRule | None = None, max_history: int = 100) -> None:
        self.rule = rule or AlertRule()
        self._history: collections.deque[AlertEvent] = collections.deque(maxlen=max_history)

    def update_rule(self, rule: AlertRule) -> None:
        self.rule = rule

    def get_history(self, limit: int = 50) -> list[AlertEvent]:
        history_list = list(self._history)
        return history_list[-limit:]

    def check_sample(self, sample: TrafficSample) -> list[AlertEvent]:
        if not self.rule.enabled:
            return []

        triggered_events: list[AlertEvent] = []
        now = datetime.now(timezone.utc)

        # Kiểm tra ngưỡng Upload
        if (
            self.rule.max_upload_bytes_per_sec is not None
            and sample.upload_bytes_per_second is not None
            and sample.upload_bytes_per_second > self.rule.max_upload_bytes_per_sec
        ):
            up_kb = sample.upload_bytes_per_second / 1000.0
            thresh_kb = self.rule.max_upload_bytes_per_sec / 1000.0
            event = AlertEvent(
                timestamp=now,
                alert_type="upload_exceeded",
                metric_name="upload_speed",
                current_value=sample.upload_bytes_per_second,
                threshold_value=self.rule.max_upload_bytes_per_sec,
                message=f"Tốc độ Upload ({up_kb:.1f} KB/s) vượt quá ngưỡng cho phép ({thresh_kb:.1f} KB/s)!",
            )
            triggered_events.append(event)
            self._history.append(event)

        # Kiểm tra ngưỡng Download
        if (
            self.rule.max_download_bytes_per_sec is not None
            and sample.download_bytes_per_second is not None
            and sample.download_bytes_per_second > self.rule.max_download_bytes_per_sec
        ):
            down_kb = sample.download_bytes_per_second / 1000.0
            thresh_kb = self.rule.max_download_bytes_per_sec / 1000.0
            event = AlertEvent(
                timestamp=now,
                alert_type="download_exceeded",
                metric_name="download_speed",
                current_value=sample.download_bytes_per_second,
                threshold_value=self.rule.max_download_bytes_per_sec,
                message=f"Tốc độ Download ({down_kb:.1f} KB/s) vượt quá ngưỡng cho phép ({thresh_kb:.1f} KB/s)!",
            )
            triggered_events.append(event)
            self._history.append(event)

        return triggered_events
    