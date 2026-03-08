from __future__ import annotations

import base64
import httpx
from typing import cast

from telegram import Message, Update, User
from telegram.ext import ContextTypes

from app.bot.i18n import t
from app.models.schemas import AlertInsert, BackendAlertPayload
from app.services.api_client import BackendApiClient
from app.services.database import DatabaseService
from app.services.storage import StorageService


async def handle_text_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    message = cast(Message, update.message)
    user = cast(User, update.effective_user)

    db: DatabaseService = context.application.bot_data["db_service"]
    api_client: BackendApiClient = context.application.bot_data["api_client"]
    telegram_user_id = str(user.id)
    senior = db.get_senior_by_telegram_user_id(telegram_user_id)

    if not senior:
        await message.reply_text(t("en", "not_registered"))
        return

    text = (message.text or "").strip()
    if not text:
        return

    try:
        alert_row = db.create_alert(
            AlertInsert(senior_id=senior.id, channel="telegram", transcription=text)
        )
        payload = BackendAlertPayload(
            alert_id=alert_row["id"],
            senior_id=senior.id,
            telegram_user_id=telegram_user_id,
            channel="telegram",
            text=text,
        )
        await api_client.send_alert(payload)
    except httpx.ReadTimeout:
        # Alert row is already created; backend processing may still be in progress.
        return
    except Exception as e:
        print(f"Error occurred while handling text alert: {e}")
        await message.reply_text(t(senior.preferred_language, "failed_alert"))


async def handle_voice_alert(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.effective_user:
        return
    message = cast(Message, update.message)
    user = cast(User, update.effective_user)

    db: DatabaseService = context.application.bot_data["db_service"]
    storage: StorageService = context.application.bot_data["storage_service"]
    api_client: BackendApiClient = context.application.bot_data["api_client"]

    telegram_user_id = str(user.id)
    senior = db.get_senior_by_telegram_user_id(telegram_user_id)
    if not senior:
        await message.reply_text(t("en", "not_registered"))
        return

    if not message.voice:
        return

    try:
        voice_file = await context.bot.get_file(message.voice.file_id)
        voice_data = await voice_file.download_as_bytearray()
        audio_bytes = bytes(voice_data)
        audio_base64 = base64.b64encode(audio_bytes).decode("ascii")

        audio_url = None
        try:
            audio_url = storage.upload_voice(
                telegram_user_id=telegram_user_id, data=audio_bytes
            )
        except Exception:
            pass

        alert_row = db.create_alert(
            AlertInsert(senior_id=senior.id, channel="telegram", audio_url=audio_url)
        )

        payload = BackendAlertPayload(
            alert_id=alert_row["id"],
            senior_id=senior.id,
            telegram_user_id=telegram_user_id,
            channel="telegram",
            audio_url=audio_url,
            audio_base64=audio_base64,
        )
        await api_client.send_alert(payload)
    except httpx.ReadTimeout:
        # Alert row is already created; backend processing may still be in progress.
        return
    except Exception as e:
        print(f"Error occurred while handling voice alert: {e}")
        await message.reply_text(t(senior.preferred_language, "failed_alert"))
