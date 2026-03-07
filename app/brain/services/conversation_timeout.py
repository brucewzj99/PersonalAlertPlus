from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from telegram import Bot

from app.config import get_settings
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)

DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 5


def _first_dict_row(data: object) -> dict[str, Any] | None:
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    return cast(dict[str, Any], first)


class ConversationTimeoutHandler:
    def __init__(self, telegram_bot: Bot | None = None) -> None:
        self._db = DatabaseService()
        self._settings = get_settings()
        self._telegram_bot = telegram_bot

    def check_and_timeout_conversations(
        self,
        timeout_seconds: int = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> list[dict[str, Any]]:
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)

        active_conversations = (
            self._db.client.table("senior_conversations")
            .select("*")
            .eq("status", "active")
            .lt("started_at", cutoff_time.isoformat())
            .execute()
        )

        results: list[dict[str, Any]] = []
        for conv in active_conversations.data or []:
            if not isinstance(conv, dict):
                continue
            result = self._handle_timeout_conversation(cast(dict[str, Any], conv))
            results.append(result)

        return results

    def _handle_timeout_conversation(
        self,
        conversation: dict[str, Any],
    ) -> dict[str, Any]:
        alert_id = str(conversation.get("alert_id") or "")
        senior_id = str(conversation.get("senior_id") or "")
        conv_id = str(conversation.get("id") or "")
        if not alert_id or not senior_id or not conv_id:
            return {
                "conversation_id": conv_id,
                "alert_id": alert_id,
                "action": "timeout_skipped_missing_fields",
            }

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

        alert_response = (
            self._db.client.table("alerts")
            .select("risk_level")
            .eq("id", alert_id)
            .limit(1)
            .execute()
        )
        alert_row = _first_dict_row(alert_response.data)
        risk_level = str((alert_row or {}).get("risk_level") or "").upper()
        if risk_level != "UNCERTAIN":
            logger.info(
                "Skipping check-in call for timed-out conversation %s (risk_level=%s)",
                conv_id,
                risk_level or "unknown",
            )
            return {
                "conversation_id": conv_id,
                "alert_id": alert_id,
                "action": "timeout_no_checkin_call",
            }

        self._trigger_check_in_call(senior_id, alert_id)

        return {
            "conversation_id": conv_id,
            "alert_id": alert_id,
            "action": "timeout_triggered",
        }

    def _trigger_check_in_call(self, senior_id: str, alert_id: str) -> None:
        senior_response = (
            self._db.client.table("seniors").select("*").eq("id", senior_id).execute()
        )
        senior = _first_dict_row(senior_response.data)
        if senior is None:
            logger.error(f" Senior not found for timeout call: {senior_id}")
            return

        phone = str(senior.get("phone_number") or "")
        lang = str(senior.get("preferred_language") or "en")

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

    def get_pending_checkin_calls(self) -> list[dict[str, Any]]:
        pending = (
            self._db.client.table("ai_actions")
            .select("*")
            .eq("action_type", "initiate_checkin_call")
            .eq("action_status", "pending")
            .execute()
        )
        rows = pending.data or []
        return [cast(dict[str, Any], row) for row in rows if isinstance(row, dict)]


def run_timeout_check() -> list[dict[str, Any]]:
    handler = ConversationTimeoutHandler()
    return handler.check_and_timeout_conversations(
        timeout_seconds=DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS
    )
