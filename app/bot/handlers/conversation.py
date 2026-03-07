from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)

from app.services.database import DatabaseService
from app.services.storage import StorageService
from app.brain.prompts import map_language_code
from app.brain.providers.openai_compatible import OpenAICompatibleClient
from app.brain.services.speech_to_text import process_audio as speech_to_text_process_audio

logger = logging.getLogger(__name__)

CONVERSATION_EXPIRY_MINUTES = 30

CONVERSATION_ACK_MESSAGES: dict[str, str] = {
    "en": "Thank you for your response. We have received your message and will use this information to help you.",
    "zh": "感谢您的回复。我们已收到您的信息，并将使用这些信息来帮助您。",
    "ms": "Terima kasih atas respons anda. Kami telah menerima mesej anda dan akan menggunakan maklumat ini untuk membantu anda.",
    "ta": "உங்கள் பதிலுக்கு நன்றி. உங்கள் செய்தியைப் பெற்றுள்ளோம்; உங்களுக்கு உதவ இந்த தகவலை பயன்படுத்துவோம்.",
    "nan": "感谢你的回复。阮已经收到你的信息，会用这些信息来帮助你。",
    "yue": "多谢你嘅回复。我哋已经收到你嘅message，会用呢啲信息帮你。",
}


def _get_conversation_ack_audio_path(language: str) -> Path | None:
    lang = language if language in CONVERSATION_ACK_MESSAGES else "en"
    audio_dir = Path(__file__).resolve().parents[3] / "assets" / "audio" / lang
    for filename in ("conversation_thank_you.mp3", "synthesize.mp3"):
        path = audio_dir / filename
        if path.exists():
            return path
    return None


def _first_dict_row(data: object) -> dict[str, Any] | None:
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    return cast(dict[str, Any], first)


async def handle_senior_conversation_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.message.from_user:
        return False

    user = update.message.from_user
    db = DatabaseService()

    try:
        senior_response = db.client.table("seniors").select("*").eq("telegram_user_id", str(user.id)).execute()
        senior = _first_dict_row(senior_response.data)
        if senior is None:
            return False
    except Exception as e:
        logger.error(f"Error finding senior: {e}")
        return False

    senior_id = str(senior["id"])
    lang = str(senior.get("preferred_language") or "en").lower()

    try:
        active_conversations = db.client.table("senior_conversations").select("*").eq("senior_id", senior_id).eq("status", "active").execute()
    except Exception as e:
        logger.error(f"Error checking conversations: {e}")
        return False

    conversation = _first_dict_row(active_conversations.data)
    if conversation is None:
        return False

    alert_id = str(conversation["alert_id"])

    message_text = update.message.text
    has_voice = update.message.voice is not None
    voice_bytes: bytes | None = None
    voice_audio_url: str | None = None
    original_message_text = (message_text or "").strip()
    message_en = original_message_text
    source_language = (senior.get("preferred_language") or "en")
    translated = False

    if has_voice:
        try:
            assert update.message.voice is not None
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            voice_bytes = bytes(await voice_file.download_as_bytearray())
            logger.info(f"Voice message captured for alert {alert_id}, size: {len(voice_bytes)} bytes")

            storage: StorageService = context.application.bot_data["storage_service"]
            voice_audio_url = storage.upload_voice(
                telegram_user_id=str(user.id),
                data=voice_bytes,
            )

            ai_client = OpenAICompatibleClient()
            stt_result = await speech_to_text_process_audio(
                ai_client,
                voice_bytes,
                preferred_language_hint=senior.get("preferred_language"),
            )
            original_message_text = (stt_result.transcript or "").strip()
            message_en = (stt_result.translated_text or stt_result.transcript or "").strip()
            source_language = stt_result.language_detected or source_language
            translated = message_en != original_message_text
        except Exception as e:
            logger.error(f"Failed to download voice: {e}")
            voice_bytes = None

    if not has_voice and original_message_text:
        preferred_language = str(senior.get("preferred_language") or "en").lower()
        source_language = preferred_language
        if preferred_language != "en":
            try:
                ai_client = OpenAICompatibleClient()
                translated_text = await ai_client.translate_text(
                    original_message_text,
                    map_language_code(preferred_language) or preferred_language,
                )
                translated_text = translated_text.strip()
                if translated_text:
                    message_en = translated_text
                    translated = message_en != original_message_text
            except Exception as e:
                logger.warning("Failed to translate senior text reply: %s", e)

    if not message_en:
        message_en = original_message_text
    if not message_en and has_voice:
        message_en = "Voice reply received (transcription unavailable)."

    db.client.table("senior_conversations").update(
        {
            "status": "completed",
            "ended_at": "now()",
            "senior_response": message_en,
        }
    ).eq("id", str(conversation["id"])).execute()

    db.client.table("ai_actions").insert(
        {
            "alert_id": alert_id,
            "action_type": "senior_conversation_reply",
            "action_status": "success",
            "details": {
                "message": message_en,
                "message_en": message_en,
                "message_original": original_message_text,
                "source_language": source_language,
                "translated": translated,
                "has_voice": has_voice,
                "audio_url": voice_audio_url,
                "conversation_id": str(conversation["id"]),
            },
        }
    ).execute()

    db.client.table("alerts").update(
        {
            "senior_response": message_en,
            "requires_operator": True,
        }
    ).eq("id", alert_id).execute()

    ack_text = CONVERSATION_ACK_MESSAGES.get(lang, CONVERSATION_ACK_MESSAGES["en"])
    ack_audio_path = _get_conversation_ack_audio_path(lang)
    if ack_audio_path is not None:
        with open(ack_audio_path, "rb") as audio_file:
            await context.bot.send_voice(
                chat_id=str(user.id),
                voice=audio_file,
                caption=f"✅ {ack_text}",
            )
    else:
        logger.warning("Missing conversation acknowledgement audio for language '%s'", lang)
        await update.message.reply_text(f"✅ {ack_text}")

    logger.info(
        f"Senior reply captured for alert {alert_id}: {message_en[:100] if message_en else '(voice)'}"
    )
    return True


async def conversation_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    
    has_voice = update.message.voice is not None
    has_text = update.message.text is not None
    
    if has_voice:
        handled = await handle_senior_conversation_reply(update, context)
        if not handled:
            from app.bot.handlers.alerts import handle_voice_alert
            await handle_voice_alert(update, context)
    elif has_text:
        handled = await handle_senior_conversation_reply(update, context)
        if not handled:
            from app.bot.handlers.alerts import handle_text_alert
            await handle_text_alert(update, context)


def build_senior_conversation_handler() -> MessageHandler:
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        conversation_dispatcher,
    )


def build_senior_conversation_voice_handler() -> MessageHandler:
    return MessageHandler(
        filters.VOICE,
        conversation_dispatcher,
    )
