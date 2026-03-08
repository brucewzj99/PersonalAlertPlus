from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.brain.schemas import RiskAnalysis

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    def __init__(self) -> None:
        from app.services.database import DatabaseService
        settings = get_settings()
        self._db = DatabaseService()
        self.base_url = settings.ai_api_base_url
        self.api_key = settings.ai_api_key
        self.api_key_stt = settings.ai_api_key_stt or settings.ai_api_key
        self.chat_model = settings.ai_chat_model
        self.transcription_model = settings.ai_transcription_model
        self.base_url_stt = settings.ai_api_base_url_stt
        self.timeout = settings.ai_request_timeout_seconds
        self.max_retries = settings.ai_max_retries
        self.temperature = settings.ai_temperature

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language_hint: str | None = None,
    ) -> tuple[str, str | None]:
        """Transcribe audio using Whisper API. Returns (transcript, detected_language)."""
        files = {
            "file": ("audio.ogg", audio_bytes, "audio/ogg"),
        }
        data = {
            "model": self.transcription_model,
            "response_format": "json",
        }
        if language_hint:
            data["language"] = language_hint
        headers = {"Authorization": f"Bearer {self.api_key_stt}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout * 2) as client:
                response = await client.post(
                    f"{self.base_url_stt}/audio/transcriptions",
                    files=files,
                    data=data,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
                transcript = result.get("text", "").strip()
                language = result.get("language", None)
                return transcript, language
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during transcription: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def translate_audio_to_english(self, audio_bytes: bytes) -> str:
        """Translate audio to English using Whisper translations endpoint (e.g. Groq).
        Use when language was detected as non-English; returns English text only."""
        files = {
            "file": ("audio.ogg", audio_bytes, "audio/ogg"),
        }
        data = {
            "model": self.transcription_model,
            "response_format": "json",
        }
        headers = {"Authorization": f"Bearer {self.api_key_stt}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout * 2) as client:
                response = await client.post(
                    f"{self.base_url_stt}/audio/translations",
                    files=files,
                    data=data,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
                return (result.get("text") or "").strip()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during translation: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Translation error: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def translate_text(self, text: str, source_language: str) -> str:
        """Translate text from source language to English."""
        from app.brain.prompts import (
            TRANSLATION_SYSTEM_PROMPT,
            TRANSLATION_USER_PROMPT,
        )

        system_prompt = TRANSLATION_SYSTEM_PROMPT.format(
            source_language=source_language
        )
        user_prompt = TRANSLATION_USER_PROMPT.format(text=text)

        response = await self._chatCompletion(
            system_message=system_prompt,
            user_message=user_prompt,
        )
        return response.strip()

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def classify_risk(
        self,
        transcript: str,
        language: str,
        senior_name: str,
        medical_notes: str | None,
        preferred_language: str | None,
    ) -> RiskAnalysis:
        """Classify risk level using the chat model."""
        from app.brain.prompts import (
            RISK_CLASSIFICATION_USER_PROMPT,
            FEW_SHOT_EXAMPLE_TEMPLATE,
            render_risk_classification_system_prompt,
        )

        medical_info = medical_notes or "None provided"
        lang_display = language or "Unknown"

        # Fetch few-shot examples
        examples = self._db.get_few_shot_examples(limit=5)
        examples_str = ""
        if examples:
            for ex in examples:
                examples_str += FEW_SHOT_EXAMPLE_TEMPLATE.format(
                    transcript=ex.transcript,
                    risk_level=ex.risk_level,
                )
        else:
            examples_str = "No examples available."

        base_prompt_template = self._db.get_prompt_setting(
            key="risk_classification_system_prompt",
            default_value=self._db.default_risk_prompt_template,
        )
        system_prompt = render_risk_classification_system_prompt(
            base_template=base_prompt_template,
            few_shot_examples=examples_str,
        )

        user_prompt = RISK_CLASSIFICATION_USER_PROMPT.format(
            senior_name=senior_name,
            medical_notes=medical_info,
            preferred_language=preferred_language or "Not specified",
            transcript=transcript,
            language=lang_display,
        )

        response = await self._chatCompletion(
            system_message=system_prompt,
            user_message=user_prompt,
            response_format="json_object",
        )

        try:
            parsed = json.loads(response)
            return RiskAnalysis(
                risk_level=parsed.get("risk_level", "UNCERTAIN"),
                risk_score=float(parsed.get("risk_score", 0.5)),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                keywords=parsed.get("keywords", []),
                recommended_actions=parsed.get("recommended_actions", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return RiskAnalysis(
                risk_level="UNCERTAIN",
                risk_score=0.5,
                reasoning=f"Failed to parse AI response: {str(e)}. Defaulted to UNCERTAIN.",
                keywords=[],
                recommended_actions=["Human review required"],
            )

    async def _chatCompletion(
        self,
        system_message: str,
        user_message: str,
        response_format: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "temperature": self.temperature,
        }
        if response_format:
            payload["response_format"] = {"type": response_format}

        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code == 401:
                raise ValueError(
                    "Chat API returned 401 Unauthorized. Check AI_API_KEY in .env (e.g. OpenRouter key from https://openrouter.ai/keys). Restart the app after changing .env."
                )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
