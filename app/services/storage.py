from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.services.database import DatabaseService


class StorageService:
    def __init__(self, db_service: DatabaseService) -> None:
        self._db = db_service
        self._bucket = get_settings().supabase_audio_bucket

    def upload_voice(self, telegram_user_id: str, data: bytes, suffix: str = ".ogg") -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        object_path = f"{telegram_user_id}/{timestamp}-{uuid4().hex}{suffix}"
        file_options: Any = {"content-type": "audio/ogg", "upsert": False}
        self._db.client.storage.from_(self._bucket).upload(
            object_path,
            data,
            file_options=file_options,
        )
        return self._db.client.storage.from_(self._bucket).get_public_url(object_path)
