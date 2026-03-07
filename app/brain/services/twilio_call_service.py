from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

CHECK_IN_CALL_MESSAGES = {
    "en": "This is your safety check. Please press 1 if you are okay, or press 2 if you need help.",
    "zh": "这是您的安全检查。如果您没事请按1，如果您需要帮助请按2。",
    "ms": "Ini adalah semakan keselamatan anda. Sila tekan 1 jika anda okay, atau tekan 2 jika anda perlukan bantuan.",
    "ta": "இது உங்கள் பாதுகாப்பு செக் ஆகும். நீங்கள் சரியாக இருப்பதுக்கு 1 ஐ அழுத்தவும், உதவி தேவைப்பட்டால் 2 ஐ அழுத்தவும்.",
    "nan": "这是阮的安全检查。如果你好请按1，若使需要帮助请按2。",
    "yue": "呢個係您嘅安全檢查。如果您冇事請撳1，如果您需要幫手請撳2。",
}


class TwilioCallService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from twilio.rest import Client

            self._client = Client(
                self._settings.twilio_account_sid,
                self._settings.twilio_auth_token,
            )
        return self._client

    def make_checkin_call(
        self,
        to_number: str,
        language: str = "en",
    ) -> dict:
        print(f"Making check-in call to {to_number} in language {language}")
        if (
            not self._settings.twilio_account_sid
            or not self._settings.twilio_auth_token
        ):
            logger.warning("Twilio not configured, skipping call")
            return {"success": False, "error": "Twilio not configured"}

        message = CHECK_IN_CALL_MESSAGES.get(language, CHECK_IN_CALL_MESSAGES["en"])

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{self._get_twilio_language(language)}">{message}</Say>
    <Gather numDigits="1" action="/api/v1/twilio/gather" method="POST">
        <Say language="{self._get_twilio_language(language)}">{message}</Say>
    </Gather>
    <Say language="{self._get_twilio_language(language)}">We did not receive a response. Goodbye.</Say>
</Response>"""

        try:
            client = self._get_client()
            call = client.calls.create(
                to=to_number,
                from_=self._settings.twilio_from_number,
                twiml=twiml,
                timeout=30,
            )
            logger.info(f"Check-in call initiated: {call.sid} to {to_number}")
            return {"success": True, "call_sid": call.sid}
        except Exception as e:
            logger.error(f"Failed to make check-in call: {e}")
            return {"success": False, "error": str(e)}

    def _get_twilio_language(self, language: str) -> str:
        mapping = {
            "en": "en-US",
            "zh": "zh-CN",
            "ms": "ms-MY",
            "ta": "ta-IN",
            "nan": "zh-CN",
            "yue": "zh-CN",
        }
        return mapping.get(language, "en-US")
