"""
Speech-to-text and translation module for PersonalAlertPlus.

Flow (aligned with agent.md §5b):
1. Detect language first via transcription (Whisper returns language).
2. If English → use transcript as-is (transcription only).
3. If non-English (e.g. Chinese) → translate to English:
   - When using Groq: use /audio/translations endpoint (transcribe + translate in one call).
   - Otherwise: translate transcript to English via LLM.

Uses Groq API when AI_API_BASE_URL_STT points to Groq (https://api.groq.com/openai/v1).
Groq translation requires whisper-large-v3 (whisper-large-v3-turbo does not support translations).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import get_settings
from app.brain.prompts import map_language_code

if TYPE_CHECKING:
    from app.brain.providers.openai_compatible import OpenAICompatibleClient

logger = logging.getLogger(__name__)

# Groq STT base URL (OpenAI-compatible); used to decide translation path
GROQ_STT_BASE = "api.groq.com"


def _looks_like_english_text(text: str) -> bool:
    sample = (text or "").strip()
    if len(sample) < 3:
        return False

    ascii_count = sum(1 for ch in sample if ord(ch) < 128)
    alpha_count = sum(1 for ch in sample if "a" <= ch.lower() <= "z")
    ascii_ratio = ascii_count / max(len(sample), 1)
    return ascii_ratio >= 0.9 and alpha_count >= 3


ENGLISH_HINT_WORDS = {
    "the",
    "and",
    "is",
    "are",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "a",
    "an",
    "to",
    "for",
    "in",
    "on",
    "my",
    "me",
    "help",
    "please",
    "pain",
    "fall",
    "cannot",
    "can't",
}


def _looks_like_meaningful_english(text: str) -> bool:
    sample = (text or "").strip().lower()
    if not sample:
        return False
    if not _looks_like_english_text(sample):
        return False

    tokens = [token for token in sample.replace("/", " ").split() if token]
    if not tokens:
        return False

    token_matches = 0
    for token in tokens[:30]:
        cleaned = "".join(ch for ch in token if ch.isalpha() or ch == "'")
        if cleaned in ENGLISH_HINT_WORDS:
            token_matches += 1

    if len(tokens) <= 6:
        return token_matches >= 1
    return token_matches >= 2


def _normalize_language_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    language_map = {
        "en": "en",
        "english": "en",
        "zh": "zh",
        "chinese": "zh",
        "ms": "ms",
        "malay": "ms",
        "ta": "ta",
        "tamil": "ta",
        "nan": "nan",
        "hokkien": "nan",
        "yue": "yue",
        "cantonese": "yue",
    }
    return language_map.get(normalized, normalized)


@dataclass
class SpeechToTextResult:
    """Result of speech-to-text and optional translation."""

    transcript: str
    language_detected: str | None
    translated_text: str | None  # English text for analysis; None if source was English


def _is_groq_stt() -> bool:
    """True if STT is configured to use Groq (so we can use /audio/translations)."""
    base = get_settings().ai_api_base_url_stt or ""
    return GROQ_STT_BASE in base


async def process_audio(
    ai_client: OpenAICompatibleClient,
    audio_bytes: bytes,
    preferred_language_hint: str | None = None,
) -> SpeechToTextResult:
    """
    Detect language, transcribe, and translate to English when needed.

    Flow:
    1. Transcribe once (Groq/Whisper) → get transcript + detected language.
    2. If English → return transcript only (no translation).
    3. If non-English (e.g. Chinese) → translate to English via Groq /audio/translations
       or LLM fallback; return transcript + translated_text.
    """
    # Step 1: Transcribe (and get language from response)
    preferred_lang = _normalize_language_code(preferred_language_hint)
    transcript, language_detected = await ai_client.transcribe_audio(audio_bytes)

    if not transcript and not language_detected:
        return SpeechToTextResult(
            transcript="",
            language_detected=language_detected,
            translated_text=None,
        )

    # Normalize language code for comparison (e.g. "en", "zh")
    lang = _normalize_language_code(language_detected)
    if not lang and _looks_like_english_text(transcript):
        lang = "en"
    if not lang and preferred_lang:
        lang = preferred_lang
    if lang != "en" and _looks_like_english_text(transcript):
        lang = "en"

    should_retry_with_preferred = (
        preferred_lang is not None
        and preferred_lang != "en"
        and lang == "en"
        and not _looks_like_meaningful_english(transcript)
    )

    if should_retry_with_preferred:
        try:
            retry_transcript, retry_language = await ai_client.transcribe_audio(
                audio_bytes,
                language_hint=preferred_lang,
            )
            if retry_transcript and retry_transcript.strip():
                transcript = retry_transcript
            retry_lang = _normalize_language_code(retry_language)
            if retry_lang:
                lang = retry_lang
            else:
                lang = preferred_lang
            language_detected = retry_language or preferred_lang
            logger.info(
                "Re-ran transcription with preferred language hint: %s",
                preferred_lang,
            )
        except Exception as e:
            logger.warning(
                "Retry transcription with preferred language hint failed: %s",
                e,
            )

    # Step 2: If English, no translation
    if lang == "en":
        return SpeechToTextResult(
            transcript=transcript,
            language_detected="en",
            translated_text=None,
        )

    # Step 3: Non-English → translate to English
    source_language = language_detected or preferred_language_hint or "unknown"
    translated_text: str | None = None

    if _is_groq_stt():
        try:
            # Groq: use /audio/translations (requires whisper-large-v3, not turbo)
            translated_text = await ai_client.translate_audio_to_english(audio_bytes)
            if not translated_text:
                translated_text = None
        except Exception as e:
            logger.warning(
                "Groq audio translation failed (%s), falling back to LLM translation",
                e,
            )
            translated_text = None

    if translated_text is None:
        # Fallback: LLM translation of the transcript
        try:
            translated_text = await ai_client.translate_text(
                transcript, map_language_code(source_language) or source_language
            )
        except Exception as e:
            logger.warning("LLM translation failed: %s", e)
            translated_text = transcript  # use original for analysis

    return SpeechToTextResult(
        transcript=transcript,
        language_detected=language_detected or source_language,
        translated_text=translated_text or None,
    )
