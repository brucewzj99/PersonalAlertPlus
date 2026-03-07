from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)

from app.services.database import DatabaseService
from app.bot.i18n import t as translate

logger = logging.getLogger(__name__)

CONVERSATION_EXPIRY_MINUTES = 30


async def handle_senior_conversation_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.message.from_user:
        return False

    user = update.message.from_user
    db = DatabaseService()

    try:
        senior_response = db.client.table("seniors").select("*").eq("telegram_user_id", str(user.id)).execute()
        if not senior_response.data:
            return False
    except Exception as e:
        logger.error(f"Error finding senior: {e}")
        return False

    senior = senior_response.data[0]
    senior_id = senior["id"]
    lang = senior.get("preferred_language", "en")

    try:
        active_conversations = db.client.table("senior_conversations").select("*").eq("senior_id", senior_id).eq("status", "active").execute()
    except Exception as e:
        logger.error(f"Error checking conversations: {e}")
        return False

    if not active_conversations.data:
        return False

    conversation = active_conversations.data[0]
    alert_id = conversation["alert_id"]

    message_text = update.message.text
    has_voice = update.message.voice is not None

    if has_voice:
        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            voice_bytes = await voice_file.download_as_bytearray()
            logger.info(f"Voice message captured for alert {alert_id}, size: {len(voice_bytes)} bytes")
        except Exception as e:
            logger.error(f"Failed to download voice: {e}")
            voice_bytes = None

    db.client.table("senior_conversations").update(
        {
            "status": "completed",
            "ended_at": "now()",
            "senior_response": message_text,
        }
    ).eq("id", conversation["id"]).execute()

    db.client.table("ai_actions").insert(
        {
            "alert_id": alert_id,
            "action_type": "senior_conversation_reply",
            "action_status": "success",
            "details": {
                "message": message_text,
                "has_voice": has_voice,
                "conversation_id": conversation["id"],
            },
        }
    ).execute()

    db.client.table("alerts").update(
        {
            "senior_response": message_text,
            "requires_operator": True,
        }
    ).eq("id", alert_id).execute()

    ack_messages = {
        "en": "Thank you for your response. We have received your message and will use this information to help you.",
        "zh": "感谢您的回复。我们已收到您的信息，并将使用这些信息来帮助您。",
        "ms": "Terima kasih atas respons anda. Kami telah menerima mesej anda dan akan menggunakan maklumat ini untuk membantu anda.",
        "ta": "உங்கள் பதிலுக்கு நன்றி. உங்கள் செய்தியைப் பெற்றுள்ளோம் உதவி.",
        "nan": "感谢你的回复。阮已经收到你的信息，会用这些信息来帮助你。",
        "yue": "多谢你嘅回复。我哋已经收到你嘅message，会用呢啲信息帮你。",
    }

    ack_text = ack_messages.get(lang, ack_messages["en"])
    await update.message.reply_text(f"✅ {ack_text}")

    logger.info(f"Senior reply captured for alert {alert_id}: {message_text[:100] if message_text else '(voice)'}")
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
