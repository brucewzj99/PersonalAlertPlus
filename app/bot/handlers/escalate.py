from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
)

from app.services.database import DatabaseService
from app.config import get_settings
from app.brain.schemas import SeniorContext, EmergencyContact
from app.brain.services.notification_service import NotificationService


SENIOR_ESCALATE_MESSAGES = {
    "en": {
        "confirmation": "Your alert has been escalated to our team. We will check on you immediately.",
        "acknowledged": "Senior {name} has escalated their alert. Notifying team now.",
    },
    "zh": {
        "confirmation": "您的警报已升级给我们的团队。我们会立即联系您。",
        "acknowledged": "长者 {name} 已升级警报。正在通知团队。",
    },
    "ms": {
        "confirmation": "Amaran anda telah diringkaskan kepada pasukan kami. Kami akan menghubungi anda dengan segera.",
        "acknowledged": "Warga emas {name} telah meningkat amaran. Memberitahu pasukan sekarang.",
    },
    "ta": {
        "confirmation": "உங்கள் எச்சரிக்கை எங்கள் குழுவுக்கு உயர்த்தப்பட்டுள்ளது. நாங்கள் உடனடியாக உங்களைத் தொடர்பு கொள்வோம்.",
        "acknowledged": "மூத்தவர் {name} தங்கள் எச்சரிக்கையை உயர்த்தியுள்ளார். குழுவுக்கு தெரியப்படுத்துகிறோம்.",
    },
    "nan": {
        "confirmation": "您的警报已经升级给阮的团队阮会紧接联系您。",
        "acknowledged": "长辈 {name} 已经升级警报。正通知团队。",
    },
    "yue": {
        "confirmation": "你嘅警报已经升级比我地团队。我地会即刻联络你。",
        "acknowledged": "老友 {name} 已经升级警报。正通知团队。",
    },
}


async def handle_escalate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback when senior clicks 'I'm not okay' button."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    if not callback_data or not callback_data.startswith("escalate:"):
        return

    alert_id = callback_data.split(":", 1)[1]
    print(f"[EscalateHandler] Processing escalation for alert: {alert_id}")

    db = DatabaseService()

    response = db.client.table("alerts").select("*").eq("id", alert_id).execute()
    if not response.data:
        await query.edit_message_text("Alert not found.")
        return

    alert = response.data[0]
    senior_id = alert["senior_id"]

    senior_response = db.client.table("seniors").select("*").eq("id", senior_id).execute()
    if not senior_response.data:
        await query.edit_message_text("Senior profile not found.")
        return

    senior_data = senior_response.data[0]
    senior = SeniorContext(
        id=senior_data["id"],
        full_name=senior_data["full_name"],
        phone_number=senior_data["phone_number"],
        address=senior_data["address"],
        preferred_language=senior_data.get("preferred_language"),
        medical_notes=senior_data.get("medical_notes"),
        birth_year=senior_data.get("birth_year"),
        birth_month=senior_data.get("birth_month"),
        birth_day=senior_data.get("birth_day"),
    )

    db.client.table("alerts").update({
        "status": "escalated",
        "requires_operator": True,
        "risk_level": "HIGH",
        "risk_score": 1.0,
    }).eq("id", alert_id).execute()

    db.client.table("ai_actions").insert({
        "alert_id": alert_id,
        "action_type": "senior_escalated",
        "action_status": "success",
        "details": {"reason": "Senior clicked 'I'm not okay' button"},
    }).execute()

    contacts_response = (
        db.client.table("emergency_contacts")
        .select("*")
        .eq("senior_id", senior_id)
        .order("priority_order")
        .execute()
    )

    contacts = []
    if contacts_response.data:
        for row in contacts_response.data:
            contacts.append(EmergencyContact(
                id=row["id"],
                senior_id=row["senior_id"],
                name=row["name"],
                relationship=row.get("relationship"),
                phone_number=row.get("phone_number"),
                telegram_user_id=row.get("telegram_user_id"),
                priority_order=row.get("priority_order", 1),
            ))

    lang = senior.preferred_language or "en"
    messages = SENIOR_ESCALATE_MESSAGES.get(lang, SENIOR_ESCALATE_MESSAGES["en"])

    await query.edit_message_text(
        f"⚠️ {messages['confirmation']}",
        parse_mode="Markdown"
    )

    if contacts:
        settings = get_settings()
        notification_service = NotificationService(
            telegram_bot=context.bot,
            enable_sms_fallback=settings.brain_enable_sms_fallback,
            notify_telegram_first=settings.brain_notify_telegram_first,
        )

        transcript = alert.get("transcription")
        audio_url = alert.get("audio_url")

        summary = f"Senior clicked 'I'm not okay' button to escalate."

        await notification_service.notify_contacts(
            contacts=contacts,
            senior=senior,
            risk_level="HIGH",
            risk_score=1.0,
            summary=summary,
            transcript=transcript,
            audio_url=audio_url,
            is_escalation=True,
        )


def build_escalate_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        handle_escalate_callback,
        pattern=r"^escalate:",
    )
