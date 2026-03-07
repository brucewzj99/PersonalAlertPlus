from __future__ import annotations

import json
import time

import httpx

from app.config import get_settings
from app.services.database import DatabaseService

# #region agent log
_DEBUG_LOG = "/Users/csl/Documents/Cursor/PABProd/PersonalAlertPlus/.cursor/debug-2dbd72.log"
def _d(loc: str, msg: str, data: dict, hid: str):
    try:
        with open(_DEBUG_LOG, "a") as f:
            f.write(json.dumps({"sessionId": "2dbd72", "timestamp": int(time.time() * 1000), "location": loc, "message": msg, "data": data, "hypothesisId": hid}) + "\n")
    except Exception:
        pass
# #endregion


class AudioFetcher:
    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self._db = db_service or DatabaseService()
        self._settings = get_settings()

    async def fetch_audio_bytes(self, audio_url: str) -> bytes:
        """Fetch audio file from Supabase Storage URL."""
        if not audio_url:
            raise ValueError("Audio URL is required")

        # #region agent log
        has_public = "/object/public/" in audio_url
        supabase_prefix = f"{self._settings.supabase_url}/storage/v1"
        starts_storage = audio_url.startswith(supabase_prefix)
        if has_public:
            branch = "public_first"
        elif starts_storage:
            branch = "supabase_storage"
        else:
            branch = "public_fallback"
        _d("audio_fetcher.py:fetch_audio_bytes", "branch check", {"has_object_public": has_public, "branch": branch, "url_prefix": audio_url[:80]}, "A")
        _d("audio_fetcher.py:fetch_audio_bytes", "branch check", {"branch": branch}, "D")
        # #endregion

        # Public bucket URLs: plain GET, no auth (auth can cause 400)
        if "/object/public/" in audio_url:
            return await self._fetch_from_public_url(audio_url)
        if audio_url.startswith(f"{self._settings.supabase_url}/storage/v1"):
            return await self._fetch_from_supabase_storage(audio_url)
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
        # #region agent log
        _d("audio_fetcher.py:_fetch_from_public_url", "public GET", {"url_prefix": url[:80]}, "B")
        _d("audio_fetcher.py:_fetch_from_public_url", "public GET", {}, "E")
        # #endregion
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            # #region agent log
            _d("audio_fetcher.py:_fetch_from_public_url", "response", {"status_code": response.status_code, "body_preview": (response.text[:500] if response.status_code >= 400 else "")}, "C")
            # #endregion
            if response.status_code >= 400 and "Bucket not found" in response.text:
                bucket_from_url = ""
                if "/object/public/" in url:
                    parts = url.split("/object/public/", 1)[-1].strip("/").split("/")
                    if parts:
                        bucket_from_url = parts[0]
                # #region agent log
                _d("audio_fetcher.py:_fetch_from_public_url", "bucket not found", {"bucket_from_url": bucket_from_url, "supabase_url": self._settings.supabase_url}, "F")
                # #endregion
                raise ValueError(
                    f"Supabase Storage: bucket '{bucket_from_url or 'alerts-audio'}' not found. Create it in Supabase Dashboard → Storage (project: {self._settings.supabase_url})."
                )
            response.raise_for_status()
            return response.content
