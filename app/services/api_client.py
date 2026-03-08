from __future__ import annotations

import httpx
from urllib.parse import urlparse

from app.config import get_settings
from app.models.schemas import BackendAlertPayload


class BackendApiClient:
    def __init__(self) -> None:
        settings = get_settings()
        configured_backend_url = settings.backend_api_url.rstrip("/")
        parsed = urlparse(configured_backend_url)
        if parsed.scheme and parsed.netloc:
            backend_origin = f"{parsed.scheme}://{parsed.netloc}"
        else:
            backend_origin = configured_backend_url

        self._ingest_url = backend_origin + "/api/v1/brain/alerts/ingest"

    async def send_alert(self, payload: BackendAlertPayload) -> None:
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=20.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self._ingest_url, json=payload.model_dump())
            response.raise_for_status()
