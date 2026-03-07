from __future__ import annotations

import httpx

from app.config import get_settings
from app.models.schemas import BackendAlertPayload


class BackendApiClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.backend_api_url.rstrip("/")

    async def send_alert(self, payload: BackendAlertPayload) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self._base_url + "/alerts/ingest", json=payload.model_dump()
            )
            response.raise_for_status()
