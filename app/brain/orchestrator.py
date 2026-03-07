from __future__ import annotations

import logging

from telegram import Bot

from app.brain.schemas import (
    BrainAlertPayload,
    BrainAlertResponse,
    EmergencyContact,
    ProcessingResult,
    RiskAnalysis,
    SeniorContext,
)
from app.brain.providers.openai_compatible import OpenAICompatibleClient
from app.brain.services.audio_fetcher import AudioFetcher
from app.brain.services.risk_engine import RiskEngine
from app.brain.services.notification_service import NotificationService
from app.brain.services.action_logger import ActionLogger
from app.brain.prompts import map_language_code
from app.services.database import DatabaseService
from app.config import get_settings

logger = logging.getLogger(__name__)

SENIOR_MESSAGES = {
    "en": {
        "low": {
            "native": "We have received your message and assessed that everything is fine. Your family members have been notified. If you need help, please don't hesitate to reach out.",
            "english": "We received your message and assessed everything is fine. Your family has been notified. Stay safe!",
        },
        "medium": {
            "native": "We have received your message. Our team will follow up with you shortly to check on your status. Your family members have been notified.",
            "english": "We received your message. Our team will follow up soon to check on you. Your family has been notified.",
        },
        "high": {
            "native": "We have received your emergency alert. We are notifying your family and the response team will be dispatched immediately to assist you.",
            "english": "Emergency received! We are notifying your family and dispatching help immediately.",
        },
    },
    "zh": {
        "low": {
            "native": "我们已经收到您的信息，经评估确认一切正常。您的家人已收到通知。如有需要，请随时联系我们。",
            "english": "We received your message and assessed everything is fine. Your family has been notified. Stay safe!",
        },
        "medium": {
            "native": "我们已经收到您的信息。团队将很快与您联系确认情况。您的家人已收到通知。",
            "english": "We received your message. Our team will follow up soon to check on you. Your family has been notified.",
        },
        "high": {
            "native": "我们已收到您的紧急求助。正在通知您的家人，救援队伍将立即前往帮助您。",
            "english": "Emergency received! We are notifying your family and dispatching help immediately.",
        },
    },
    "ms": {
        "low": {
            "native": "Kami telah menerima mesej anda dan menilai bahawa semuanya baik-baik sahaja. Keluarga anda telah dimaklumkan.",
            "english": "We received your message and assessed everything is fine. Your family has been notified. Stay safe!",
        },
        "medium": {
            "native": "Kami telah menerima mesej anda. Pasukan kami akan menghubungi anda tidak lama lagi. Keluarga anda telah dimaklumkan.",
            "english": "We received your message. Our team will follow up soon to check on you. Your family has been notified.",
        },
        "high": {
            "native": "Kami telah menerima amaran kecemasan anda. Kami sedang memberitahu keluarga anda dan pasukan bantuan akan dihantar dengan segera.",
            "english": "Emergency received! We are notifying your family and dispatching help immediately.",
        },
    },
    "ta": {
        "low": {
            "native": "உங்கள் செய்தியைப் பெற்றோம். எல்லாமே சரியாக உள்ளதாக மதிப்பிட்டோம். உங்கள் குடும்பத்தினருக்கு தெரியப்படுத்தப்பட்டது.",
            "english": "We received your message and assessed everything is fine. Your family has been notified. Stay safe!",
        },
        "medium": {
            "native": "உங்கள் செய்தியைப் பெற்றோம். எங்கள் குழு விரைவில் உங்களைத் தொடர்பு கொள்ளும். உங்கள் குடும்பத்தினருக்கு தெரியப்படுத்தப்பட்டது.",
            "english": "We received your message. Our team will follow up soon to check on you. Your family has been notified.",
        },
        "high": {
            "native": "உங்கள் அவசர எச்சரிக்கை பெறப்பட்டது! உங்கள் குடும்பத்தினருக்கு தெரியப்படுத்தி உதவி உடனடியாக அனுப்பப்படுகிறது.",
            "english": "Emergency received! We are notifying your family and dispatching help immediately.",
        },
    },
    "nan": {
        "low": {
            "native": "阮已经收到您的信息，评估一切正常。您的家人已经通知。",
            "english": "We received your message and assessed everything is fine. Your family has been notified. Stay safe!",
        },
        "medium": {
            "native": "阮已经收到您的信息。团队会联系您确认情况。您的家人已经通知。",
            "english": "We received your message. Our team will follow up soon to check on you. Your family has been notified.",
        },
        "high": {
            "native": "阮已经收到您的紧急求助。正在通知您的家人，救援队伍会立刻去帮助您。",
            "english": "Emergency received! We are notifying your family and dispatching help immediately.",
        },
    },
    "yue": {
        "low": {
            "native": "我哋已經收到你嘅信息，評估一切正常。你嘅家人已經通知咗。",
            "english": "We received your message and assessed everything is fine. Your family has been notified. Stay safe!",
        },
        "medium": {
            "native": "我哋已經收到你嘅信息。團隊會聯繫你確認情況。你嘅家人已經通知咗。",
            "english": "We received your message. Our team will follow up soon to check on you. Your family has been notified.",
        },
        "high": {
            "native": "我哋已經收到你嘅緊急求助。正通知你嘅家人，救援隊伍會即刻去幫你。",
            "english": "Emergency received! We are notifying your family and dispatching help immediately.",
        },
    },
}


class BrainOrchestrator:
    def __init__(self, telegram_bot: Bot | None = None) -> None:
        print("[BrainOrchestrator] Initializing...")
        self._db = DatabaseService()
        self._ai_client = OpenAICompatibleClient()
        self._audio_fetcher = AudioFetcher(self._db)
        self._risk_engine = RiskEngine()
        self._action_logger = ActionLogger(self._db)
        settings = get_settings()
        self._telegram_bot = telegram_bot

        self._notification_service = NotificationService(
            telegram_bot=telegram_bot,
            enable_sms_fallback=settings.brain_enable_sms_fallback,
            notify_telegram_first=settings.brain_notify_telegram_first,
        )
        print("[BrainOrchestrator] Initialization complete")

    async def process_alert(self, payload: BrainAlertPayload) -> BrainAlertResponse:
        """Main orchestration entry point."""
        print(f"\n{'='*60}")
        print(f"[BrainOrchestrator] >>> START PROCESSING ALERT")
        print(f"[BrainOrchestrator] Senior ID: {payload.senior_id}")
        print(f"[BrainOrchestrator] Channel: {payload.channel}")
        print(f"[BrainOrchestrator] Has audio: {bool(payload.audio_url)}")
        print(f"[BrainOrchestrator] Has text: {bool(payload.text)}")
        print(f"{'='*60}\n")

        try:
            result = await self._process_alert_internal(payload)
            if result.error:
                print(f"[BrainOrchestrator] <<< ALERT FAILED: {result.error}")
                return BrainAlertResponse(
                    ok=False,
                    alert_id=result.alert_id,
                    processing_status="failed",
                    error=result.error,
                )
            print(
                f"[BrainOrchestrator] <<< ALERT COMPLETED - Risk: {result.analysis.risk_level if result.analysis else 'N/A'}, Score: {result.analysis.risk_score if result.analysis else 'N/A'}"
            )
            return BrainAlertResponse(
                ok=True,
                alert_id=result.alert_id,
                processing_status="completed",
                risk_level=result.analysis.risk_level if result.analysis else None,
                risk_score=(
                    float(result.analysis.risk_score) if result.analysis else None
                ),
            )
        except Exception as e:
            logger.exception(f"Unexpected error processing alert: {e}")
            print(f"[BrainOrchestrator] <<< ALERT EXCEPTION: {e}")
            return BrainAlertResponse(
                ok=False,
                processing_status="failed",
                error=str(e),
            )

    async def _process_alert_internal(
        self, payload: BrainAlertPayload
    ) -> ProcessingResult:
        print("[BrainOrchestrator] Step 1: Fetching senior profile...")
        senior = self._get_senior(payload.senior_id)
        if not senior:
            print(f"[BrainOrchestrator] ERROR: Senior not found: {payload.senior_id}")
            return ProcessingResult(
                alert_id="",
                status="failed",
                error=f"Senior not found: {payload.senior_id}",
            )
        print(
            f"[BrainOrchestrator] Senior found: {senior.full_name} (lang: {senior.preferred_language})"
        )

        print("[BrainOrchestrator] Step 2: Creating alert record in database...")
        alert_record = self._create_alert_record(payload, senior)
        alert_id = alert_record["id"]
        print(f"[BrainOrchestrator] Alert record created: {alert_id}")

        try:
            self._update_alert_status(alert_id, "processing")
            print("[BrainOrchestrator] Alert status: processing")
        except Exception:
            pass

        content = payload.text
        language_detected = None

        if payload.audio_url:
            print("[BrainOrchestrator] Step 3a: Processing voice message...")
            try:
                print(f"[BrainOrchestrator] Fetching audio from: {payload.audio_url}")
                audio_bytes = await self._audio_fetcher.fetch_audio_bytes(
                    payload.audio_url
                )
                print(
                    f"[BrainOrchestrator] Audio fetched ({len(audio_bytes)} bytes), transcribing..."
                )
                transcript, language_detected = await self._ai_client.transcribe_audio(
                    audio_bytes
                )
                print(
                    f"[BrainOrchestrator] Transcription complete: '{transcript}' (lang: {language_detected})"
                )
                content = transcript

                self._action_logger.log_transcription(
                    alert_id=alert_id,
                    success=True,
                    language=language_detected,
                )
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                print(f"[BrainOrchestrator] Transcription FAILED: {e}")
                self._action_logger.log_transcription(
                    alert_id=alert_id,
                    success=False,
                    error=str(e),
                )
                if payload.text:
                    content = payload.text
                    print("[BrainOrchestrator] Falling back to text input")
                else:
                    return ProcessingResult(
                        alert_id=alert_id,
                        status="failed",
                        error=f"Transcription failed and no text input: {e}",
                    )
        else:
            print("[BrainOrchestrator] Step 3b: Processing text message...")

        if not content:
            print("[BrainOrchestrator] ERROR: No content to analyze")
            return ProcessingResult(
                alert_id=alert_id,
                status="failed",
                error="No content to analyze",
            )

        print(
            f"[BrainOrchestrator] Step 4: Language detection (preferred: {senior.preferred_language})"
        )
        source_language = map_language_code(senior.preferred_language)
        translated_text = None

        if language_detected and language_detected.lower() != "en":
            print(
                f"[BrainOrchestrator] Step 5: Translating from {language_detected} to English..."
            )
            try:
                translated_text = await self._ai_client.translate_text(
                    content, source_language
                )
                print(f"[BrainOrchestrator] Translation complete: '{translated_text}'")
            except Exception as e:
                logger.warning(f"Translation failed: {e}")
                print(
                    f"[BrainOrchestrator] Translation FAILED: {e}, using original text"
                )
                translated_text = content
        elif language_detected:
            source_language = language_detected

        print(
            f"[BrainOrchestrator] Step 6: Risk classification (text: '{translated_text or content}')..."
        )
        analysis = await self._ai_client.classify_risk(
            transcript=translated_text or content,
            language=source_language,
            senior_name=senior.full_name,
            medical_notes=senior.medical_notes,
            preferred_language=senior.preferred_language,
        )
        print(
            f"[BrainOrchestrator] Initial classification: {analysis.risk_level} ({analysis.risk_score})"
        )

        print("[BrainOrchestrator] Step 7: Applying guardrails...")
        analysis = self._risk_engine.apply_guardrails(
            analysis, translated_text or content, senior.medical_notes
        )
        print(
            f"[BrainOrchestrator] Final classification: {analysis.risk_level} ({analysis.risk_score})"
        )
        print(f"[BrainOrchestrator] Reasoning: {analysis.reasoning}")
        print(f"[BrainOrchestrator] Keywords: {analysis.keywords}")

        self._action_logger.log_classification(
            alert_id=alert_id,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            success=True,
        )

        summary = self._risk_engine.generate_summary(
            senior_name=senior.full_name,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            reasoning=analysis.reasoning,
            keywords=analysis.keywords,
        )
        print(f"[BrainOrchestrator] Summary generated")

        requires_operator = analysis.risk_level in ["HIGH", "MEDIUM"]
        status = "escalated" if analysis.risk_level == "HIGH" else "pending"

        print(
            f"[BrainOrchestrator] Step 8: Updating alert in database (risk: {analysis.risk_level}, requires_operator: {requires_operator})"
        )
        self._update_alert_complete(
            alert_id=alert_id,
            transcription=content,
            language_detected=source_language,
            translated_text=translated_text,
            risk_level=analysis.risk_level,
            risk_score=analysis.risk_score,
            analysis_summary=summary,
            keywords=analysis.keywords,
            requires_operator=requires_operator,
            status=status,
        )

        print(
            f"[BrainOrchestrator] Step 9: Handling risk actions for {analysis.risk_level}..."
        )
        if analysis.risk_level in ["HIGH", "MEDIUM", "LOW"]:
            await self._handle_risk_actions(
                alert_id=alert_id,
                risk_level=analysis.risk_level,
                senior=senior,
                summary=summary,
                transcript=content,
                audio_url=payload.audio_url,
            )

        print(f"[BrainOrchestrator] Step 10: Sending confirmation to senior...")
        await self._send_senior_confirmation(
            telegram_user_id=payload.telegram_user_id,
            senior=senior,
            risk_level=analysis.risk_level,
            alert_id=alert_id,
        )

        return ProcessingResult(
            alert_id=alert_id,
            transcription=content,
            language_detected=source_language,
            translated_text=translated_text,
            analysis=analysis,
            analysis_summary=summary,
            status="completed",
        )

    async def _send_senior_confirmation(
        self,
        telegram_user_id: str,
        senior: SeniorContext,
        risk_level: str,
        alert_id: str | None = None,
    ) -> None:
        """Send confirmation message to senior via Telegram."""
        if not self._telegram_bot or not telegram_user_id:
            print(
                "[BrainOrchestrator] Cannot send confirmation: no Telegram bot or user ID"
            )
            return

        lang = senior.preferred_language or "en"
        risk_key = risk_level.lower()

        messages = SENIOR_MESSAGES.get(lang, SENIOR_MESSAGES["en"])
        risk_messages = messages.get(risk_key, messages["low"])

        emoji_map = {"high": "🚨", "medium": "⚠️", "low": "✅"}
        emoji = emoji_map.get(risk_key, "ℹ️")

        confirmation_text = f"{emoji} *Status Update*\n\n"
        confirmation_text += f"_{risk_messages['native']}_\n\n"
        confirmation_text += f"---\n\n"
        confirmation_text += f"{risk_messages['english']}"

        inline_keyboard = None

        if risk_key in ["low", "medium"] and alert_id:
            not_okay_text = {
                "en": "I'm not okay",
                "zh": "我不舒服",
                "ms": "Saya tidak baik",
                "ta": "எனக்கு பிரச்சினை இருக்கு",
                "nan": "我不舒服",
                "yue": "我唔舒服",
            }
            btn_text = not_okay_text.get(lang, not_okay_text["en"])

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            inline_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(btn_text, callback_data=f"escalate:{alert_id}")]]
            )

        try:
            await self._telegram_bot.send_message(
                chat_id=telegram_user_id,
                text=confirmation_text,
                parse_mode="Markdown",
                reply_markup=inline_keyboard,
            )
            print(f"[BrainOrchestrator] Confirmation sent to senior {senior.full_name}")
        except Exception as e:
            print(f"[BrainOrchestrator] Failed to send confirmation to senior: {e}")

    def _get_senior(self, senior_id: str) -> SeniorContext | None:
        response = (
            self._db.client.table("seniors").select("*").eq("id", senior_id).execute()
        )
        if not response.data:
            return None
        data = response.data[0]
        return SeniorContext(
            id=data["id"],
            full_name=data["full_name"],
            phone_number=data["phone_number"],
            address=data["address"],
            preferred_language=data.get("preferred_language"),
            medical_notes=data.get("medical_notes"),
            birth_year=data.get("birth_year"),
            birth_month=data.get("birth_month"),
            birth_day=data.get("birth_day"),
        )

    def _get_emergency_contacts(self, senior_id: str) -> list[EmergencyContact]:
        response = (
            self._db.client.table("emergency_contacts")
            .select("*")
            .eq("senior_id", senior_id)
            .order("priority_order")
            .execute()
        )
        if not response.data:
            return []
        return [
            EmergencyContact(
                id=row["id"],
                senior_id=row["senior_id"],
                name=row["name"],
                relationship=row.get("relationship"),
                phone_number=row.get("phone_number"),
                telegram_user_id=row.get("telegram_user_id"),
                priority_order=row.get("priority_order", 1),
            )
            for row in response.data
        ]

    def _create_alert_record(
        self, payload: BrainAlertPayload, senior: SeniorContext
    ) -> dict:
        response = (
            self._db.client.table("alerts")
            .insert(
                {
                    "senior_id": payload.senior_id,
                    "channel": payload.channel,
                    "audio_url": payload.audio_url,
                    "transcription": payload.text,
                    "processing_status": "pending",
                }
            )
            .execute()
        )
        return response.data[0]

    def _update_alert_status(self, alert_id: str, status: str) -> None:
        self._db.client.table("alerts").update({"processing_status": status}).eq(
            "id", alert_id
        ).execute()

    def _update_alert_complete(
        self,
        alert_id: str,
        transcription: str,
        language_detected: str,
        translated_text: str | None,
        risk_level: str,
        risk_score: float,
        analysis_summary: str,
        keywords: list[str],
        requires_operator: bool,
        status: str,
    ) -> None:
        self._db.client.table("alerts").update(
            {
                "transcription": transcription,
                "language_detected": language_detected,
                "translated_text": translated_text,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "analysis_summary": analysis_summary,
                "keywords": keywords,
                "requires_operator": requires_operator,
                "status": status,
                "processing_status": "completed",
            }
        ).eq("id", alert_id).execute()

    async def _handle_risk_actions(
        self,
        alert_id: str,
        risk_level: str,
        senior: SeniorContext,
        summary: str,
        transcript: str | None = None,
        audio_url: str | None = None,
    ) -> None:
        contacts = self._get_emergency_contacts(senior.id)

        if not contacts:
            self._action_logger.log_action(
                alert_id=alert_id,
                action_type="notify_family",
                action_status="failed",
                details={"error": "No emergency contacts found"},
            )
            return

        results = await self._notification_service.notify_contacts(
            contacts=contacts,
            senior=senior,
            risk_level=risk_level,
            risk_score=1.0,
            summary=summary,
            transcript=transcript,
            audio_url=audio_url,
        )

        for result in results:
            self._action_logger.log_notification_sent(
                alert_id=alert_id,
                contact_name=result.get("recipient", "unknown"),
                channel=result.get("channel", "unknown"),
                success=result.get("success", False),
                external_ref=result.get("external_ref"),
                error=result.get("error"),
            )
