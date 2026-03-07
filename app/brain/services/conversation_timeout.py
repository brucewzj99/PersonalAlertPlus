from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import Bot

from app.config import get_settings
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)


class ConversationTimeoutHandler:
    def __init__(self, telegram_bot: Bot | None = None) -> None:
        self._db = DatabaseService()
        self._settings = get_settings()
        self._telegram_bot = telegram_bot

    def check_and_timeout_conversations(self, timeout_minutes: int = 1) -> list[dict[str, Any]]:
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        active_conversations = (
            self._db.client.table("senior_conversations")
            .select("*")
            .eq("status", "active")
            .lt("started_at", cutoff_time.isoformat())
            .execute()
        )

        results = []
        for conv in active_conversations.data:
            result = self._handle_timeout_conversation(conv)
            results.append(result)

        return results

    def _handle_timeout_conversation(self, conversation: dict) -> dict:
        alert_id = conversation["alert_id"]
        senior_id = conversation["senior_id"]
        conv_id = conversation["id"]

        logger.info(f"Timeout for conversation {conv_id}, alert {alert_id}")

        self._db.client.table("senior_conversations").update(
            {
                "status": "timeout",
                "ended_at": "now()",
            }
        ).eq("id", conv_id).execute()

        self._db.client.table("ai_actions").insert(
            {
                "alert_id": alert_id,
                "action_type": "conversation_timeout",
                "action_status": "success",
                "details": {"conversation_id": conv_id},
            }
        ).execute()

        self._trigger_check_in_call(senior_id, alert_id)

        return {
            "conversation_id": conv_id,
            "alert_id": alert_id,
            "action": "timeout_triggered",
        }

    def _trigger_check_in_call(self, senior_id: str, alert_id: str) -> None:
        senior_response = self._db.client.table("seniors").select("*").eq("id", senior_id).execute()
        if not senior_response.data:
            logger.error(f" Senior not found for timeout call: {senior_id}")
            return

        senior = senior_response.data[0]
        phone = senior.get("phone_number")
        lang = senior.get("preferred_language", "en")

        if not phone:
            logger.error(f"No phone number for senior {senior_id}")
            return

        from app.brain.services.twilio_call_service import TwilioCallService

        call_service = TwilioCallService()
        result = call_service.make_checkin_call(phone, lang)

        action_status = "success" if result.get("success") else "failed"
        self._db.client.table("ai_actions").insert(
            {
                "alert_id": alert_id,
                "action_type": "checkin_call",
                "action_status": action_status,
                "details": {
                    "senior_id": senior_id,
                    "phone": phone,
                    "language": lang,
                    "call_sid": result.get("call_sid"),
                    "error": result.get("error"),
                },
            }
        ).execute()

        logger.info(f"Check-in call result for senior {senior_id}: {result}")

    def get_pending_checkin_calls(self) -> list[dict]:
        pending = (
            self._db.client.table("ai_actions")
            .select("*")
            .eq("action_type", "initiate_checkin_call")
            .eq("action_status", "pending")
            .execute()
        )
        return pending.data


def run_timeout_check() -> list[dict[str, Any]]:
    handler = ConversationTimeoutHandler()
    return handler.check_and_timeout_conversations(timeout_minutes=1)
