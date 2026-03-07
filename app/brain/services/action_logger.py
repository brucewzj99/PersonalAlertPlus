from __future__ import annotations

from typing import Any

from app.services.database import DatabaseService


class ActionLogger:
    def __init__(self, db_service: DatabaseService | None = None) -> None:
        self._db = db_service or DatabaseService()

    def log_action(
        self,
        alert_id: str,
        action_type: str,
        action_status: str = "pending",
        details: dict[str, Any] | None = None,
        provider: str | None = None,
        external_ref: str | None = None,
        error_message: str | None = None,
        attempt_count: int = 1,
    ) -> dict[str, Any]:
        """Log an AI action to the database."""
        payload: dict[str, Any] = {
            "alert_id": alert_id,
            "action_type": action_type,
            "action_status": action_status,
            "details": details,
            "provider": provider,
            "external_ref": external_ref,
            "error_message": error_message,
            "attempt_count": attempt_count,
        }

        response = self._db.client.table("ai_actions").insert(payload).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return {}

    def log_notification_sent(
        self,
        alert_id: str,
        contact_name: str,
        channel: str,
        success: bool,
        external_ref: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Convenience method for logging notification results."""
        return self.log_action(
            alert_id=alert_id,
            action_type="notify_family",
            action_status="success" if success else "failed",
            details={
                "contact_name": contact_name,
                "channel": channel,
                "message": f"Emergency notification sent to {contact_name} via {channel}",
            },
            provider=channel,
            external_ref=external_ref,
            error_message=error,
        )

    def log_transcription(
        self,
        alert_id: str,
        success: bool,
        language: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Log transcription result."""
        return self.log_action(
            alert_id=alert_id,
            action_type="transcribe_audio",
            action_status="success" if success else "failed",
            details={"language": language},
            error_message=error,
        )

    def log_classification(
        self,
        alert_id: str,
        risk_level: str,
        risk_score: float,
        success: bool,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Log risk classification result."""
        return self.log_action(
            alert_id=alert_id,
            action_type="classify_risk",
            action_status="success" if success else "failed",
            details={
                "risk_level": risk_level,
                "risk_score": risk_score,
            },
            error_message=error,
        )
