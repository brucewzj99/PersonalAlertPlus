from __future__ import annotations

import base64
import logging
from typing import Any, cast

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
from app.brain.services.speech_to_text import (
    process_audio as speech_to_text_process_audio,
)
from app.brain.services.risk_engine import RiskEngine
from app.brain.services.notification_service import NotificationService
from app.brain.services.action_logger import ActionLogger
from app.brain.prompts import map_language_code
from app.services.database import DatabaseService
from app.services.storage import StorageService
from app.config import get_settings

logger = logging.getLogger(__name__)

# Map to DB constraint: Supabase alerts_risk_level_check allows URGENT, NON_URGENT, UNCERTAIN, FALSE_ALARM (uppercase)
def _risk_level_for_db(raw: str) -> str:
    allowed = ("URGENT", "NON_URGENT", "UNCERTAIN", "FALSE_ALARM")
    normalized = (raw or "").strip().upper()
    return normalized if normalized in allowed else "UNCERTAIN"


SENIOR_MESSAGES = {
    "en": {
        "false_alarm": {
            "native": "Sorry, this does not look like a service request. If you still need help, please tap Escalate.",
            "english": "Sorry, this does not look like a service request. If you still need help, tap Escalate.",
        },
        "uncertain": {
            "native": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
            "english": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
        },
        "non_urgent": {
            "native": "We received your alert. We are notifying your family and escalating this as non-urgent follow-up.",
            "english": "We received your alert. Your family has been notified and this is escalated as non-urgent.",
        },
        "urgent": {
            "native": "We have received your emergency alert. We are notifying your family and escalating to operations as urgent priority.",
            "english": "Emergency received. We are notifying your family and escalating to operations with urgent priority.",
        },
    },
    "zh": {
        "false_alarm": {
            "native": "抱歉，这看起来不是服务请求。如果您仍需要帮助，请点击“升级处理”。",
            "english": "Sorry, this does not look like a service request. If you still need help, tap Escalate.",
        },
        "uncertain": {
            "native": "我们暂时无法完全确认您的情况。请确认您是否平安，若需要协助请点击“升级处理”。",
            "english": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
        },
        "non_urgent": {
            "native": "我们已收到您的警报。正在通知家属，并以非紧急个案升级给运营团队跟进。",
            "english": "We received your alert. Your family has been notified and this is escalated as non-urgent.",
        },
        "urgent": {
            "native": "我们已收到您的紧急警报。正在通知家属，并以紧急优先级升级给运营团队。",
            "english": "Emergency received. We are notifying your family and escalating to operations with urgent priority.",
        },
    },
    "ms": {
        "false_alarm": {
            "native": "Maaf, ini nampaknya bukan permintaan bantuan. Jika anda masih perlukan bantuan, tekan Eskalasi.",
            "english": "Sorry, this does not look like a service request. If you still need help, tap Escalate.",
        },
        "uncertain": {
            "native": "Kami masih tidak pasti tentang keadaan anda. Sila sahkan anda okay, atau tekan Eskalasi jika perlukan bantuan.",
            "english": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
        },
        "non_urgent": {
            "native": "Kami telah menerima amaran anda. Keluarga anda dimaklumkan dan kes ini dinaikkan sebagai bukan kecemasan.",
            "english": "We received your alert. Your family has been notified and this is escalated as non-urgent.",
        },
        "urgent": {
            "native": "Kami telah menerima amaran kecemasan anda. Kami memaklumkan keluarga dan menaikkan kepada operasi sebagai keutamaan segera.",
            "english": "Emergency received. We are notifying your family and escalating to operations with urgent priority.",
        },
    },
    "ta": {
        "false_alarm": {
            "native": "மன்னிக்கவும், இது சேவை கோரிக்கையாக தெரியவில்லை. இன்னும் உதவி தேவைப்பட்டால் 'Escalate' ஐ அழுத்தவும்.",
            "english": "Sorry, this does not look like a service request. If you still need help, tap Escalate.",
        },
        "uncertain": {
            "native": "உங்கள் நிலைமை பற்றி முழுமையாக உறுதியாக இல்லை. நீங்கள் நலமா என்று உறுதிசெய்யவும், உதவி வேண்டும் என்றால் Escalate அழுத்தவும்.",
            "english": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
        },
        "non_urgent": {
            "native": "உங்கள் எச்சரிக்கை பெறப்பட்டது. உங்கள் குடும்பத்தினருக்கு தெரிவிக்கப்பட்டு, இது அவசரமல்லாததாக குழுவிற்கு உயர்த்தப்பட்டுள்ளது.",
            "english": "We received your alert. Your family has been notified and this is escalated as non-urgent.",
        },
        "urgent": {
            "native": "உங்கள் அவசர எச்சரிக்கை பெறப்பட்டது. உங்கள் குடும்பத்தினருக்கு தெரிவித்து, செயல்பாட்டு குழுவிற்கு மிக அவசர முன்னுரிமையுடன் உயர்த்தப்பட்டுள்ளது.",
            "english": "Emergency received. We are notifying your family and escalating to operations with urgent priority.",
        },
    },
    "nan": {
        "false_alarm": {
            "native": "歹势，这看起来毋是服务请求。若你阁需要帮助，请按 Escalate。",
            "english": "Sorry, this does not look like a service request. If you still need help, tap Escalate.",
        },
        "uncertain": {
            "native": "阮暂时袂完全确定你的情况。请确认你是否平安，若需要帮忙请按 Escalate。",
            "english": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
        },
        "non_urgent": {
            "native": "阮已经收到你的警报。你的家人会收到通知，也会用非紧急案件升级给团队。",
            "english": "We received your alert. Your family has been notified and this is escalated as non-urgent.",
        },
        "urgent": {
            "native": "阮已经收到你的紧急警报。会通知家人，并以紧急优先升级到运营团队。",
            "english": "Emergency received. We are notifying your family and escalating to operations with urgent priority.",
        },
    },
    "yue": {
        "false_alarm": {
            "native": "唔好意思，呢个睇落唔似服务请求。如果你仲需要帮手，请按 Escalate。",
            "english": "Sorry, this does not look like a service request. If you still need help, tap Escalate.",
        },
        "uncertain": {
            "native": "我哋暂时未能完全确认你嘅情况。请确认你是否安全；如需协助，请按 Escalate。",
            "english": "We are not fully sure about your situation yet. Please confirm if you are okay, or tap Escalate if you need assistance.",
        },
        "non_urgent": {
            "native": "我哋已经收到你嘅警报。你嘅家人会收到通知，个案亦会以非紧急方式升级跟进。",
            "english": "We received your alert. Your family has been notified and this is escalated as non-urgent.",
        },
        "urgent": {
            "native": "我哋已经收到你嘅紧急警报。会通知你嘅家人，并以紧急优先级升级到运营团队。",
            "english": "Emergency received. We are notifying your family and escalating to operations with urgent priority.",
        },
    },
}


class BrainOrchestrator:
    def __init__(self, telegram_bot: Bot | None = None) -> None:
        print("[BrainOrchestrator] Initializing...")
        self._db = DatabaseService()
        self._storage = StorageService(self._db)
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

        print("[BrainOrchestrator] Step 2: Creating/updating alert record in database...")
        alert_record = self._create_or_get_alert_record(payload, senior)
        alert_id = alert_record["id"]
        print(f"[BrainOrchestrator] Alert record ready: {alert_id}")

        try:
            self._update_alert_status(alert_id, "processing")
            print("[BrainOrchestrator] Alert status: processing")
        except Exception:
            pass

        content = payload.text
        language_detected = None
        translated_text = None
        audio_url = payload.audio_url
        inline_audio_bytes: bytes | None = None

        if payload.audio_base64:
            inline_audio_bytes = base64.b64decode(payload.audio_base64)
            if not audio_url:
                try:
                    audio_url = self._storage.upload_voice(
                        telegram_user_id=payload.telegram_user_id or payload.senior_id,
                        data=inline_audio_bytes,
                    )
                    print(
                        "[BrainOrchestrator] Uploaded inline audio to Supabase Storage for dashboard playback"
                    )
                except Exception as e:
                    logger.warning("Failed to store inline audio for dashboard: %s", e)

        has_voice = bool(inline_audio_bytes or audio_url)
        if has_voice:
            print(
                "[BrainOrchestrator] Step 3a: Processing voice message (detect → transcribe/translate)..."
            )
            try:
                if inline_audio_bytes is not None:
                    audio_bytes = inline_audio_bytes
                    print(
                        f"[BrainOrchestrator] Using inline audio from Telegram ({len(audio_bytes)} bytes), running speech-to-text..."
                    )
                else:
                    if audio_url is None:
                        raise RuntimeError("Audio URL missing for voice alert")
                    print(
                        f"[BrainOrchestrator] Fetching audio from: {audio_url}"
                    )
                    audio_bytes = await self._audio_fetcher.fetch_audio_bytes(
                        audio_url
                    )
                    print(
                        f"[BrainOrchestrator] Audio fetched ({len(audio_bytes)} bytes), running speech-to-text..."
                    )
                stt_result = await speech_to_text_process_audio(
                    self._ai_client,
                    audio_bytes,
                    preferred_language_hint=senior.preferred_language,
                )
                content = stt_result.transcript
                language_detected = stt_result.language_detected
                translated_text = stt_result.translated_text
                print(
                    f"[BrainOrchestrator] Transcription: '{content}' (lang: {language_detected}, translated: {bool(translated_text)})"
                )
                if translated_text:
                    print(f"[BrainOrchestrator] English text: '{translated_text}'")

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
            preferred_lang = (senior.preferred_language or "en").strip().lower()
            language_detected = preferred_lang
            if content:
                if preferred_lang == "en":
                    translated_text = content
                else:
                    try:
                        translated_candidate = await self._ai_client.translate_text(
                            content,
                            map_language_code(preferred_lang) or preferred_lang,
                        )
                        translated_text = translated_candidate.strip() or content
                    except Exception as e:
                        logger.warning("Text translation failed: %s", e)
                        translated_text = content
            else:
                translated_text = None

        if not content:
            print("[BrainOrchestrator] ERROR: No content to analyze")
            return ProcessingResult(
                alert_id=alert_id,
                status="failed",
                error="No content to analyze",
            )

        print(
            f"[BrainOrchestrator] Step 4: Language (detected: {language_detected}, preferred: {senior.preferred_language})"
        )
        source_language = (
            map_language_code(language_detected or senior.preferred_language)
            or language_detected
            or map_language_code(senior.preferred_language)
        )

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

        requires_operator = analysis.risk_level in ["URGENT", "NON_URGENT"]
        if analysis.risk_level in ["URGENT", "NON_URGENT"]:
            status = "escalated"
        elif analysis.risk_level == "FALSE_ALARM":
            status = "closed"
        else:
            status = "pending_confirmation"

        print(
            f"[BrainOrchestrator] Step 8: Updating alert in database (risk: {analysis.risk_level}, requires_operator: {requires_operator})"
        )
        language_detected_db = language_detected or senior.preferred_language or "en"
        raw_risk = (analysis.risk_level or "MEDIUM").lower()
        risk_level_db = _risk_level_for_db(raw_risk)
        status_db = status.lower()
        print(
            f"[BrainOrchestrator] DEBUG DB write: alert_id={alert_id} risk_level_db={risk_level_db!r} status_db={status_db!r} language_detected_db={language_detected_db!r}"
        )
        self._update_alert_complete(
            alert_id=alert_id,
            audio_url=audio_url,
            transcription=content,
            language_detected=language_detected_db,
            translated_text=translated_text,
            risk_level=risk_level_db,
            risk_score=analysis.risk_score,
            analysis_summary=summary,
            keywords=analysis.keywords,
            requires_operator=requires_operator,
            status=status,
        )

        print(
            f"[BrainOrchestrator] Step 9: Handling risk actions for {analysis.risk_level}..."
        )
        if analysis.risk_level in ["URGENT", "NON_URGENT", "UNCERTAIN", "FALSE_ALARM"]:
            await self._handle_risk_actions(
                alert_id=alert_id,
                risk_level=analysis.risk_level,
                senior=senior,
                summary=summary,
                risk_score=analysis.risk_score,
                transcript=content,
                audio_url=audio_url,
            )

        print(f"[BrainOrchestrator] Step 10: Sending confirmation to senior...")
        send_check_in = analysis.risk_level == "UNCERTAIN"
        send_need_info = analysis.risk_level in ["URGENT", "NON_URGENT"]

        if send_need_info and alert_id:
            self._db.client.table("senior_conversations").insert(
                {
                    "senior_id": senior.id,
                    "alert_id": alert_id,
                    "status": "active",
                }
            ).execute()
            print(
                f"[BrainOrchestrator] Created conversation record for alert {alert_id}"
            )

        await self._send_senior_confirmation(
            telegram_user_id=payload.telegram_user_id,
            senior=senior,
            risk_level=analysis.risk_level,
            alert_id=alert_id,
            send_check_in_audio=send_check_in,
            send_need_info_audio=send_need_info,
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
        send_check_in_audio: bool = False,
        send_need_info_audio: bool = False,
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
        risk_messages = messages.get(risk_key, messages["uncertain"])

        emoji_map = {
            "urgent": "🚨",
            "non_urgent": "⚠️",
            "uncertain": "❓",
            "false_alarm": "ℹ️",
        }
        emoji = emoji_map.get(risk_key, "ℹ️")

        confirmation_text = f"{emoji} *Status Update*\n\n"
        confirmation_text += f"_{risk_messages['native']}_\n\n"
        confirmation_text += f"---\n\n"
        confirmation_text += f"{risk_messages['english']}"

        inline_keyboard = None

        if risk_key == "uncertain" and alert_id:
            confirm_text = {
                "en": "I am okay",
                "zh": "我没事",
                "ms": "Saya okay",
                "ta": "நான் நலமாக இருக்கிறேன்",
                "nan": "我没代志",
                "yue": "我无事",
            }
            escalate_text = {
                "en": "Escalate",
                "zh": "升级处理",
                "ms": "Eskalasi",
                "ta": "Escalate",
                "nan": "升级处理",
                "yue": "升级处理",
            }

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            inline_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            confirm_text.get(lang, confirm_text["en"]),
                            callback_data=f"confirm_ok:{alert_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            escalate_text.get(lang, escalate_text["en"]),
                            callback_data=f"escalate_non_urgent:{alert_id}",
                        )
                    ],
                ]
            )
        elif risk_key == "false_alarm" and alert_id:
            escalate_text = {
                "en": "Escalate",
                "zh": "升级处理",
                "ms": "Eskalasi",
                "ta": "Escalate",
                "nan": "升级处理",
                "yue": "升级处理",
            }

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            inline_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            escalate_text.get(lang, escalate_text["en"]),
                            callback_data=f"escalate_non_urgent:{alert_id}",
                        )
                    ]
                ]
            )

        try:
            if send_check_in_audio and risk_level.lower() == "uncertain":
                from app.bot.check_in_messages import get_check_in_message
                import os

                check_in_msg = get_check_in_message(lang)
                audio_filename = check_in_msg["audio_file"]
                audio_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "assets",
                    "audio",
                    lang,
                    audio_filename,
                )

                with open(audio_path, "rb") as audio_file:
                    await self._telegram_bot.send_voice(
                        chat_id=telegram_user_id,
                        voice=audio_file,
                        caption=check_in_msg["text"],
                        reply_markup=inline_keyboard,
                    )
                print(
                    f"[BrainOrchestrator] Check-in audio sent to senior {senior.full_name} ({lang})"
                )
            elif send_need_info_audio and risk_level.lower() in [
                "urgent",
                "non_urgent",
            ]:
                from app.bot.check_in_messages import get_need_info_message
                import os

                need_info_msg = get_need_info_message(lang)
                audio_filename = need_info_msg["audio_file"]
                audio_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "assets",
                    "audio",
                    lang,
                    audio_filename,
                )

                with open(audio_path, "rb") as audio_file:
                    await self._telegram_bot.send_voice(
                        chat_id=telegram_user_id,
                        voice=audio_file,
                        caption=need_info_msg["text"],
                    )
                print(
                    f"[BrainOrchestrator] Need-info audio sent to senior {senior.full_name} ({lang})"
                )
            else:
                await self._telegram_bot.send_message(
                    chat_id=telegram_user_id,
                    text=confirmation_text,
                    parse_mode="Markdown",
                    reply_markup=inline_keyboard,
                )
                print(
                    f"[BrainOrchestrator] Confirmation sent to senior {senior.full_name}"
                )
        except Exception as e:
            print(f"[BrainOrchestrator] Failed to send confirmation to senior: {e}")

    def _get_senior(self, senior_id: str) -> SeniorContext | None:
        response = (
            self._db.client.table("seniors").select("*").eq("id", senior_id).execute()
        )
        rows = response.data if isinstance(response.data, list) else []
        if not rows:
            return None
        data = rows[0]
        if not isinstance(data, dict):
            return None
        senior = cast(dict[str, Any], data)
        return SeniorContext(
            id=str(senior.get("id") or ""),
            full_name=str(senior.get("full_name") or ""),
            phone_number=str(senior.get("phone_number") or ""),
            address=str(senior.get("address") or ""),
            preferred_language=cast(str | None, senior.get("preferred_language")),
            medical_notes=cast(str | None, senior.get("medical_notes")),
            birth_year=cast(int | None, senior.get("birth_year")),
            birth_month=cast(int | None, senior.get("birth_month")),
            birth_day=cast(int | None, senior.get("birth_day")),
        )

    def _get_emergency_contacts(self, senior_id: str) -> list[EmergencyContact]:
        response = (
            self._db.client.table("emergency_contacts")
            .select("*")
            .eq("senior_id", senior_id)
            .order("priority_order")
            .execute()
        )
        rows = response.data if isinstance(response.data, list) else []
        if not rows:
            return []
        dict_rows = [cast(dict[str, Any], row) for row in rows if isinstance(row, dict)]
        return [
            EmergencyContact(
                id=str(row.get("id") or ""),
                senior_id=str(row.get("senior_id") or ""),
                name=str(row.get("name") or ""),
                relationship=row.get("relationship"),
                phone_number=row.get("phone_number"),
                telegram_user_id=row.get("telegram_user_id"),
                priority_order=int(row.get("priority_order", 1) or 1),
                notify_on_uncertain=bool(row.get("notify_on_uncertain", False)),
            )
            for row in dict_rows
        ]

    def _create_or_get_alert_record(
        self, payload: BrainAlertPayload, senior: SeniorContext
    ) -> dict:
        if payload.alert_id:
            existing = self._get_alert_by_id(payload.alert_id)
            if existing and str(existing.get("senior_id")) == payload.senior_id:
                update_payload: dict[str, Any] = {
                    "processing_status": "pending",
                    "processing_error": None,
                }
                if payload.text is not None:
                    update_payload["transcription"] = payload.text
                if payload.audio_url is not None:
                    update_payload["audio_url"] = payload.audio_url

                self._db.client.table("alerts").update(update_payload).eq(
                    "id", payload.alert_id
                ).execute()
                refreshed = self._get_alert_by_id(payload.alert_id)
                if refreshed:
                    return refreshed

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
        rows = response.data if isinstance(response.data, list) else []
        first = rows[0] if rows else {}
        return cast(dict[str, Any], first if isinstance(first, dict) else {})

    def _get_alert_by_id(self, alert_id: str) -> dict | None:
        response = self._db.client.table("alerts").select("*").eq("id", alert_id).limit(
            1
        ).execute()
        rows = response.data or []
        if not rows:
            return None
        first = rows[0]
        return cast(dict[str, Any], first if isinstance(first, dict) else None)

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
        audio_url: str | None = None,
    ) -> None:
        # Normalize risk_level for DB: constraint allows URGENT, NON_URGENT, UNCERTAIN, FALSE_ALARM (uppercase)
        risk_level_normalized = _risk_level_for_db(risk_level or "UNCERTAIN")
        print(f"[BrainOrchestrator] DEBUG _update_alert_complete: alert_id={alert_id} risk_level={risk_level!r} -> db={risk_level_normalized!r} status={status!r}")
        update_payload: dict[str, Any] = {
                "transcription": transcription,
                "language_detected": language_detected,
                "translated_text": translated_text,
                "risk_level": risk_level_normalized,
                "risk_score": risk_score,
                "analysis_summary": analysis_summary,
                "keywords": keywords,
                "requires_operator": requires_operator,
                "status": status,
                "processing_status": "completed",
                "processing_error": None,
                "resolved_by": "ai",
            }
        if audio_url is not None:
            update_payload["audio_url"] = audio_url
        self._db.client.table("alerts").update(update_payload).eq("id", alert_id).execute()
        print(f"[BrainOrchestrator] DEBUG Alert updated in Supabase: {alert_id}")

    async def _handle_risk_actions(
        self,
        alert_id: str,
        risk_level: str,
        senior: SeniorContext,
        summary: str,
        risk_score: float,
        transcript: str | None = None,
        audio_url: str | None = None,
    ) -> None:
        if risk_level in ["UNCERTAIN", "FALSE_ALARM"]:
            return

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
            risk_score=risk_score,
            summary=summary,
            transcript=transcript,
            audio_url=audio_url,
        )

        self._action_logger.log_action(
            alert_id=alert_id,
            action_type="escalate_to_operator",
            action_status="success",
            details={
                "priority": "urgent" if risk_level == "URGENT" else "non-urgent",
                "risk_level": risk_level,
            },
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
