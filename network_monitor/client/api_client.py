import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

class ApiClient:
    """HTTP REST Client giao tiếp với Server qua httpx."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=5.0)

    async def check_health(self) -> Dict[str, Any]:
        response = await self._client.get("/api/health")
        response.raise_for_status()
        return response.json()

    async def get_interfaces(self, include_all: bool = False) -> List[Dict[str, Any]]:
        response = await self._client.get("/api/interfaces", params={"include_all": include_all})
        response.raise_for_status()
        data = response.json()
        return data.get("interfaces", [])

    async def get_current_statistics(self) -> Dict[str, Any]:
        response = await self._client.get("/api/statistics/current")
        response.raise_for_status()
        return response.json()

    async def start_capture(self, interface: Optional[str] = None) -> Dict[str, Any]:
        params = {"interface": interface} if interface else {}
        response = await self._client.post("/api/capture/start", params=params)
        response.raise_for_status()
        return response.json()

    async def stop_capture(self) -> Dict[str, Any]:
        response = await self._client.post("/api/capture/stop")
        response.raise_for_status()
        return response.json()

    async def get_capture_status(self) -> Dict[str, Any]:
        response = await self._client.get("/api/capture/status")
        response.raise_for_status()
        return response.json()

    async def get_recent_packets(self, limit: int = 50) -> List[Dict[str, Any]]:
        response = await self._client.get("/api/capture/packets", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def get_analytics_summary(self, top_n: int = 5) -> Dict[str, Any]:
        response = await self._client.get("/api/analytics/summary", params={"top_n": top_n})
        response.raise_for_status()
        return response.json()

    # --- APIs mới cho Bước 4 (Traffic Alerting & Data History) ---

    async def set_alert_config(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Cập nhật cấu hình ngưỡng cảnh báo xuống Server."""
        response = await self._client.post("/api/alerts/config", json=rule)
        response.raise_for_status()
        return response.json()

    async def get_alert_config(self) -> Dict[str, Any]:
        """Lấy cấu hình ngưỡng cảnh báo hiện tại từ Server."""
        response = await self._client.get("/api/alerts/config")
        response.raise_for_status()
        return response.json()

    async def get_alert_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các sự kiện cảnh báo đã xảy ra."""
        response = await self._client.get("/api/alerts/history", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()
        