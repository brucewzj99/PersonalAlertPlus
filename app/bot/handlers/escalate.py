from __future__ import annotations

from typing import Any, cast

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.services.database import DatabaseService
from app.config import get_settings
from app.brain.schemas import SeniorContext, EmergencyContact
from app.brain.services.notification_service import NotificationService


SENIOR_CALLBACK_MESSAGES = {
    "en": {
        "escalate_confirmation": "Your alert has been escalated as non-urgent. We have notified your family and operations team.",
        "escalate_confirmation_urgent": "Your alert has been escalated as urgent. We have notified your family and operations team.",
        "confirm_ok": "Thanks for confirming. We are marking this alert as resolved.",
        "skip_follow_up": "Understood. We won't ask for extra follow-up details now.",
        "follow_up_closed": "The follow-up window has already ended.",
    },
    "zh": {
        "escalate_confirmation": "您的警报已升级为非紧急个案。我们已通知家属和运营团队。",
        "escalate_confirmation_urgent": "您的警报已升级为紧急个案。我们已通知家属和运营团队。",
        "confirm_ok": "感谢确认。我们将把此警报标记为已处理。",
        "skip_follow_up": "已了解。我们暂时不会再要求您补充后续信息。",
        "follow_up_closed": "后续补充时间已结束。",
    },
    "ms": {
        "escalate_confirmation": "Amaran anda telah dinaikkan sebagai bukan kecemasan. Keluarga dan pasukan operasi telah dimaklumkan.",
        "escalate_confirmation_urgent": "Amaran anda telah dinaikkan sebagai kecemasan. Keluarga dan pasukan operasi telah dimaklumkan.",
        "confirm_ok": "Terima kasih atas pengesahan. Kami akan tandakan amaran ini sebagai selesai.",
        "skip_follow_up": "Faham. Kami tidak akan meminta maklumat susulan tambahan sekarang.",
        "follow_up_closed": "Tempoh susulan telah tamat.",
    },
    "ta": {
        "escalate_confirmation": "உங்கள் எச்சரிக்கை அவசரமல்லாததாக உயர்த்தப்பட்டுள்ளது. குடும்பத்தினரும் செயல்பாட்டு குழுவும் அறிவிக்கப்பட்டுள்ளனர்.",
        "escalate_confirmation_urgent": "உங்கள் எச்சரிக்கை அவசரமாக உயர்த்தப்பட்டுள்ளது. குடும்பத்தினரும் செயல்பாட்டு குழுவும் அறிவிக்கப்பட்டுள்ளனர்.",
        "confirm_ok": "உறுதிப்படுத்தியதற்கு நன்றி. இந்த எச்சரிக்கையை முடிக்கப்பட்டதாக குறிக்கிறோம்.",
        "skip_follow_up": "புரிந்தது. தற்போது கூடுதல் தொடர்ச்சி தகவலை கேட்கமாட்டோம்.",
        "follow_up_closed": "தொடர்ச்சி பதில் நேரம் ஏற்கனவே முடிந்துவிட்டது.",
    },
    "nan": {
        "escalate_confirmation": "你的警报已经升级做非紧急案件。阮已经通知家属佮团队。",
        "escalate_confirmation_urgent": "你的警报已经升级做紧急案件。阮已经通知家属佮团队。",
        "confirm_ok": "感谢你确认。阮会共这条警报标记做处理完成。",
        "skip_follow_up": "了解。暂时袂阁请你补充后续资讯。",
        "follow_up_closed": "后续回复时间已经结束。",
    },
    "yue": {
        "escalate_confirmation": "你嘅警报已经升级为非紧急个案。我哋已经通知家人同运营团队。",
        "escalate_confirmation_urgent": "你嘅警报已经升级为紧急个案。我哋已经通知家人同运营团队。",
        "confirm_ok": "多谢确认。我哋会将呢个警报标记为已处理。",
        "skip_follow_up": "明白。我哋而家唔会再要求你补充后续资料。",
        "follow_up_closed": "后续回复时间已经结束。",
    },
}


def _first_dict_row(data: object) -> dict[str, Any] | None:
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    return cast(dict[str, Any], first)


async def handle_escalate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    assert query is not None
    await query.answer()

    callback_data = query.data or ""
    if not (
        callback_data.startswith("escalate_non_urgent:")
        or callback_data.startswith("escalate_urgent:")
        or callback_data.startswith("confirm_ok:")
        or callback_data.startswith("skip_follow_up:")
    ):
        return

    action, alert_id = callback_data.split(":", 1)
    db = DatabaseService()

    response = db.client.table("alerts").select("*").eq("id", alert_id).execute()
    alert = _first_dict_row(response.data)
    if alert is None:
        await query.edit_message_text("Alert not found.")
        return

    senior_id = str(alert.get("senior_id") or "")
    if not senior_id:
        await query.edit_message_text("Alert not found.")
        return

    senior_response = db.client.table("seniors").select("*").eq("id", senior_id).execute()
    senior_data = _first_dict_row(senior_response.data)
    if senior_data is None:
        await query.edit_message_text("Senior profile not found.")
        return

    senior = SeniorContext(
        id=str(senior_data.get("id") or ""),
        full_name=str(senior_data.get("full_name") or ""),
        phone_number=str(senior_data.get("phone_number") or ""),
        address=str(senior_data.get("address") or ""),
        preferred_language=cast(str | None, senior_data.get("preferred_language")),
        medical_notes=cast(str | None, senior_data.get("medical_notes")),
        birth_year=cast(int | None, senior_data.get("birth_year")),
        birth_month=cast(int | None, senior_data.get("birth_month")),
        birth_day=cast(int | None, senior_data.get("birth_day")),
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

    def _complete_active_conversation(reason: str) -> None:
        conversation_response = (
            db.client.table("senior_conversations")
            .select("*")
            .eq("alert_id", alert_id)
            .eq("senior_id", senior_id)
            .eq("status", "active")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        conversation = _first_dict_row(conversation_response.data)
        if conversation is None:
            return

        conversation_id = str(conversation.get("id") or "")
        if not conversation_id:
            return

        db.client.table("senior_conversations").update(
            {
                "status": "completed",
                "ended_at": "now()",
                "senior_response": reason,
            }
        ).eq("id", conversation_id).execute()

    if action == "confirm_ok":
        _complete_active_conversation("[senior confirmed okay]")

        db.client.table("alerts").update(
            {
                "status": "closed",
                "is_resolved": True,
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

    if action == "skip_follow_up":
        conversation_response = (
            db.client.table("senior_conversations")
            .select("*")
            .eq("alert_id", alert_id)
            .eq("senior_id", senior_id)
            .eq("status", "active")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if not conversation_response.data:
            await _finalize_callback_message(messages["follow_up_closed"], "ℹ️")
            return

        conversation = _first_dict_row(conversation_response.data)
        if conversation is None:
            await _finalize_callback_message(messages["follow_up_closed"], "ℹ️")
            return

        conversation_id = str(conversation.get("id") or "")
        if not conversation_id:
            await _finalize_callback_message(messages["follow_up_closed"], "ℹ️")
            return

        db.client.table("senior_conversations").update(
            {
                "status": "completed",
                "ended_at": "now()",
                "senior_response": "[senior skipped follow-up]",
            }
        ).eq("id", conversation_id).execute()

        db.client.table("ai_actions").insert(
            {
                "alert_id": alert_id,
                "action_type": "senior_skipped_follow_up",
                "action_status": "success",
                "details": {"conversation_id": conversation_id},
            }
        ).execute()

        await _finalize_callback_message(messages["skip_follow_up"], "⏭️")
        return

    escalates_to_urgent = action == "escalate_urgent"
    risk_level = "URGENT" if escalates_to_urgent else "NON_URGENT"
    risk_score = 0.9 if escalates_to_urgent else 0.7

    db.client.table("alerts").update(
        {
            "status": "escalated",
            "requires_operator": True,
            "risk_level": risk_level,
            "risk_score": risk_score,
        }
    ).eq("id", alert_id).execute()

    _complete_active_conversation("[senior escalated via callback]")

    db.client.table("ai_actions").insert(
        {
            "alert_id": alert_id,
            "action_type": (
                "senior_escalated_to_urgent"
                if escalates_to_urgent
                else "senior_escalated_to_non_urgent"
            ),
            "action_status": "success",
            "details": {"reason": "Senior clicked escalate button"},
        }
    ).execute()

    confirmation_key = (
        "escalate_confirmation_urgent"
        if escalates_to_urgent
        else "escalate_confirmation"
    )
    await _finalize_callback_message(
        messages.get(confirmation_key, messages["escalate_confirmation"]),
        "🚨" if escalates_to_urgent else "⚠️",
    )

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
            if not isinstance(row, dict):
                continue
            priority_raw = row.get("priority_order")
            priority_order = priority_raw if isinstance(priority_raw, int) and priority_raw > 0 else 1
            contacts.append(
                EmergencyContact(
                    id=str(row.get("id") or ""),
                    senior_id=str(row.get("senior_id") or ""),
                    name=str(row.get("name") or ""),
                    relationship=cast(str | None, row.get("relationship")),
                    phone_number=cast(str | None, row.get("phone_number")),
                    telegram_user_id=cast(str | None, row.get("telegram_user_id")),
                    priority_order=priority_order,
                    notify_on_uncertain=bool(row.get("notify_on_uncertain", False)),
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
        summary = (
            "Senior reported issues from uncertain follow-up and requested urgent escalation."
            if escalates_to_urgent
            else "Senior requested escalation from uncertain/false-alarm follow-up."
        )

        await notification_service.notify_contacts(
            contacts=contacts,
            senior=senior,
            risk_level=risk_level,
            risk_score=risk_score,
            summary=summary,
            transcript=transcript,
            audio_url=audio_url,
            is_escalation=True,
        )


def build_escalate_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        handle_escalate_callback,
        pattern=r"^(escalate_non_urgent|escalate_urgent|confirm_ok|skip_follow_up):",
    )
