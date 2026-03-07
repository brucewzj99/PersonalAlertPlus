from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.services.database import DatabaseService
from app.config import get_settings
from app.brain.schemas import SeniorContext, EmergencyContact
from app.brain.services.notification_service import NotificationService


SENIOR_CALLBACK_MESSAGES = {
    "en": {
        "escalate_confirmation": "Your alert has been escalated as non-urgent. We have notified your family and operations team.",
        "confirm_ok": "Thanks for confirming. We are marking this alert as resolved.",
    },
    "zh": {
        "escalate_confirmation": "您的警报已升级为非紧急个案。我们已通知家属和运营团队。",
        "confirm_ok": "感谢确认。我们将把此警报标记为已处理。",
    },
    "ms": {
        "escalate_confirmation": "Amaran anda telah dinaikkan sebagai bukan kecemasan. Keluarga dan pasukan operasi telah dimaklumkan.",
        "confirm_ok": "Terima kasih atas pengesahan. Kami akan tandakan amaran ini sebagai selesai.",
    },
    "ta": {
        "escalate_confirmation": "உங்கள் எச்சரிக்கை அவசரமல்லாததாக உயர்த்தப்பட்டுள்ளது. குடும்பத்தினரும் செயல்பாட்டு குழுவும் அறிவிக்கப்பட்டுள்ளனர்.",
        "confirm_ok": "உறுதிப்படுத்தியதற்கு நன்றி. இந்த எச்சரிக்கையை முடிக்கப்பட்டதாக குறிக்கிறோம்.",
    },
    "nan": {
        "escalate_confirmation": "你的警报已经升级做非紧急案件。阮已经通知家属佮团队。",
        "confirm_ok": "感谢你确认。阮会共这条警报标记做处理完成。",
    },
    "yue": {
        "escalate_confirmation": "你嘅警报已经升级为非紧急个案。我哋已经通知家人同运营团队。",
        "confirm_ok": "多谢确认。我哋会将呢个警报标记为已处理。",
    },
}


async def handle_escalate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    assert query is not None
    await query.answer()

    callback_data = query.data or ""
    if not (callback_data.startswith("escalate_non_urgent:") or callback_data.startswith("confirm_ok:")):
        return

    action, alert_id = callback_data.split(":", 1)
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

    lang = senior.preferred_language or "en"
    messages = SENIOR_CALLBACK_MESSAGES.get(lang, SENIOR_CALLBACK_MESSAGES["en"])

    async def _finalize_callback_message(response_text: str, prefix: str) -> None:
        rendered = f"{prefix} {response_text}"

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=rendered,
        )

    if action == "confirm_ok":
        db.client.table("alerts").update(
            {
                "status": "closed",
                "requires_operator": False,
                "resolved_by": "senior",
            }
        ).eq("id", alert_id).execute()

        db.client.table("ai_actions").insert(
            {
                "alert_id": alert_id,
                "action_type": "senior_confirmed_ok",
                "action_status": "success",
                "details": {"reason": "Senior clicked confirmation button"},
            }
        ).execute()

        await _finalize_callback_message(messages["confirm_ok"], "✅")
        return

    db.client.table("alerts").update(
        {
            "status": "escalated",
            "requires_operator": True,
            "risk_level": "NON_URGENT",
            "risk_score": 0.7,
        }
    ).eq("id", alert_id).execute()

    db.client.table("ai_actions").insert(
        {
            "alert_id": alert_id,
            "action_type": "senior_escalated_to_non_urgent",
            "action_status": "success",
            "details": {"reason": "Senior clicked escalate button"},
        }
    ).execute()

    await _finalize_callback_message(messages["escalate_confirmation"], "⚠️")

    contacts_response = (
        db.client.table("emergency_contacts")
        .select("*")
        .eq("senior_id", senior_id)
        .order("priority_order")
        .execute()
    )

    contacts: list[EmergencyContact] = []
    if contacts_response.data:
        for row in contacts_response.data:
            contacts.append(
                EmergencyContact(
                    id=row["id"],
                    senior_id=row["senior_id"],
                    name=row["name"],
                    relationship=row.get("relationship"),
                    phone_number=row.get("phone_number"),
                    telegram_user_id=row.get("telegram_user_id"),
                    priority_order=row.get("priority_order", 1),
                    notify_on_uncertain=row.get("notify_on_uncertain", False),
                )
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
        summary = "Senior requested escalation from uncertain/false-alarm follow-up."

        await notification_service.notify_contacts(
            contacts=contacts,
            senior=senior,
            risk_level="NON_URGENT",
            risk_score=0.7,
            summary=summary,
            transcript=transcript,
            audio_url=audio_url,
            is_escalation=True,
        )


def build_escalate_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        handle_escalate_callback,
        pattern=r"^(escalate_non_urgent|confirm_ok):",
    )
