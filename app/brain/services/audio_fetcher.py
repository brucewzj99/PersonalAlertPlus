from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.database import DatabaseService


class AudioFetcher:
    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self._db = db_service or DatabaseService()
        self._settings = get_settings()

    async def fetch_audio_bytes(self, audio_url: str) -> bytes:
        """Fetch audio file from Supabase Storage URL."""
        if not audio_url:
            raise ValueError("Audio URL is required")

        if audio_url.startswith(f"{self._settings.supabase_url}/storage/v1"):
            return await self._fetch_from_supabase_storage(audio_url)
        elif audio_url.startswith(f"{self._settings.supabase_url}"):
            return await self._fetch_from_public_url(audio_url)
        else:
            return await self._fetch_from_public_url(audio_url)

    async def _fetch_from_supabase_storage(self, url: str) -> bytes:
        """Download from Supabase Storage using authenticated request."""
        headers = {
            "Authorization": f"Bearer {self._settings.supabase_secret_key}",
            "apikey": self._settings.supabase_secret_key,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.content

    async def _fetch_from_public_url(self, url: str) -> bytes:
        """Download from publicly accessible URL."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
