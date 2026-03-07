from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from telegram import Bot

from app.config import get_settings
from app.brain.schemas import EmergencyContact, SeniorContext

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    @abstractmethod
    async def send(
        self,
        contact: EmergencyContact,
        message: str,
        senior: SeniorContext,
    ) -> dict[str, Any]:
        """Send notification and return result with status."""
        pass


class TelegramNotificationChannel(NotificationChannel):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(
        self,
        contact: EmergencyContact,
        message: str,
        senior: SeniorContext,
    ) -> dict[str, Any]:
        """Send notification via Telegram."""
        if not contact.telegram_user_id:
            return {
                "success": False,
                "error": "No Telegram ID",
                "channel": "telegram",
            }

        try:
            await self.bot.send_message(
                chat_id=contact.telegram_user_id,
                text=message,
                parse_mode="Markdown",
            )
            return {
                "success": True,
                "channel": "telegram",
                "recipient": contact.telegram_user_id,
            }
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "channel": "telegram",
            }


class TwilioSMSChannel(NotificationChannel):
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        messaging_service_sid: str | None = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.messaging_service_sid = messaging_service_sid
        self._client = None

    def _get_client(self):
        if self._client is None:
            from twilio.rest import Client
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    async def send(
        self,
        contact: EmergencyContact,
        message: str,
        senior: SeniorContext,
    ) -> dict[str, Any]:
        """Send notification via Twilio SMS."""
        if not contact.phone_number:
            return {
                "success": False,
                "error": "No phone number",
                "channel": "sms",
            }

        try:
            client = self._get_client()
            msg_params = {
                "body": message,
                "to": contact.phone_number,
            }
            if self.messaging_service_sid:
                msg_params["messaging_service_sid"] = self.messaging_service_sid
            else:
                msg_params["from_"] = self.from_number

            twilio_message = client.messages.create(**msg_params)

            return {
                "success": True,
                "channel": "sms",
                "recipient": contact.phone_number,
                "external_ref": twilio_message.sid,
            }
        except Exception as e:
            logger.error(f"Twilio SMS send failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "channel": "sms",
            }


class NotificationService:
    def __init__(
        self,
        telegram_bot: Bot | None = None,
        enable_sms_fallback: bool = True,
        notify_telegram_first: bool = True,
    ) -> None:
        settings = get_settings()
        self.enable_sms_fallback = enable_sms_fallback
        self.notify_telegram_first = notify_telegram_first

        self.channels: list[NotificationChannel] = []
        self.sms_channel: TwilioSMSChannel | None = None

        if telegram_bot and notify_telegram_first:
            self.channels.append(TelegramNotificationChannel(telegram_bot))

        if enable_sms_fallback and settings.twilio_account_sid and settings.twilio_auth_token:
            self.sms_channel = TwilioSMSChannel(
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
                from_number=settings.twilio_from_number,
                messaging_service_sid=settings.twilio_messaging_service_sid,
            )
            if not notify_telegram_first or not telegram_bot:
                self.channels.append(self.sms_channel)
            else:
                self.channels.append(self.sms_channel)

    def format_emergency_message(
        self,
        senior: SeniorContext,
        risk_level: str,
        risk_score: float,
        summary: str,
        transcript: str | None = None,
        audio_url: str | None = None,
        is_escalation: bool = False,
    ) -> str:
        """Format the emergency notification message."""
        emoji_map = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}
        emoji = emoji_map.get(risk_level, "⚪")

        header = "🚨 SENIOR ESCALATED ALERT" if is_escalation else f"{emoji} EMERGENCY ALERT"

        parts = [
            header,
            "",
            f"Senior: {senior.full_name}",
            f"Phone: {senior.phone_number}",
            f"Address: {senior.address}",
            "",
        ]

        if transcript:
            parts.extend([
                f"Message: \"{transcript}\"",
                "",
            ])
        elif audio_url:
            parts.extend([
                "Message: (Voice message sent)",
                "",
            ])

        parts.extend([
            f"Risk Level: {risk_level} ({risk_score:.0%})",
            "",
            "Assessment:",
            summary,
            "",
            "—",
            "PersonalAlertPlus",
        ])

        return "\n".join(parts)

    async def notify_contacts(
        self,
        contacts: list[EmergencyContact],
        senior: SeniorContext,
        risk_level: str,
        risk_score: float,
        summary: str,
        transcript: str | None = None,
        audio_url: str | None = None,
        is_escalation: bool = False,
    ) -> list[dict[str, Any]]:
        """Notify all emergency contacts. Returns list of results."""
        if not contacts:
            return [{"success": False, "error": "No contacts to notify"}]

        message = self.format_emergency_message(
            senior, risk_level, risk_score, summary,
            transcript=transcript, audio_url=audio_url, is_escalation=is_escalation
        )

        sorted_contacts = sorted(contacts, key=lambda c: c.priority_order)
        results = []

        for contact in sorted_contacts:
            for channel in self.channels:
                result = await channel.send(contact, message, senior)
                results.append(result)

                if result.get("success"):
                    break

        return results
