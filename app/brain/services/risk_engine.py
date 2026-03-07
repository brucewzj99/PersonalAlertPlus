from app.brain.schemas import RiskAnalysis
from app.brain.prompts import detect_emergency_keywords


def _ascii_ratio(text: str) -> float:
    if not text:
        return 0.0
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    return ascii_count / max(len(text), 1)


def _trim_for_reason(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _translation_suspicion_reason(original_text: str, translated_text: str) -> str | None:
    original = (original_text or "").strip()
    translated = (translated_text or "").strip()
    if not translated:
        return "translated text is empty"

    original_ascii = _ascii_ratio(original)
    translated_ascii = _ascii_ratio(translated)
    length_ratio = len(translated) / max(len(original), 1)

    reasons: list[str] = []

    if original and translated and original.casefold() == translated.casefold() and original_ascii < 0.75:
        reasons.append("translated text is identical to non-English transcript")
    if translated_ascii < 0.7:
        reasons.append("translated text does not look like English")
    if length_ratio < 0.2 or length_ratio > 4.0:
        reasons.append("translation length is unusually different from source")

    translated_lower = translated.lower()
    if "???" in translated or "[inaudible]" in translated_lower or "[unintelligible]" in translated_lower:
        reasons.append("translation contains placeholder or unclear tokens")

    if not reasons:
        return None
    return "; ".join(reasons[:2])


class RiskEngine:
    @staticmethod
    def apply_guardrails(
        analysis: RiskAnalysis,
        transcript: str,
        medical_notes: str | None,
        original_transcript: str | None = None,
        translated_text: str | None = None,
    ) -> RiskAnalysis:
        """Apply safety guardrails to AI classification."""
        keywords_found = detect_emergency_keywords(transcript)
        medical_conditions = ["hypertension", "diabetes", "heart", "mobility", "stroke"]

        has_critical_medical = False
        if medical_notes:
            notes_lower = medical_notes.lower()
            for condition in medical_conditions:
                if condition in notes_lower:
                    has_critical_medical = True
                    break

        final_risk_level = analysis.risk_level
        final_risk_score = analysis.risk_score
        final_reasoning = analysis.reasoning

        if keywords_found and analysis.risk_level == "FALSE_ALARM":
            final_risk_level = "NON_URGENT"
            final_risk_score = max(0.5, final_risk_score)
            final_reasoning = (
                f"Elevated to NON_URGENT due to emergency keywords: {', '.join(keywords_found)}. "
                f"{final_reasoning}"
            )

        if keywords_found and any(
            kw in ["fall", "fell", "unconscious", "chest pain", "can't breathe"]
            for kw in keywords_found
        ):
            final_risk_level = "URGENT"
            final_risk_score = max(0.85, final_risk_score)
            final_reasoning = (
                f"Elevated to URGENT due to critical emergency keywords: {', '.join(keywords_found)}. "
                f"{final_reasoning}"
            )

        if has_critical_medical and final_risk_level in ["FALSE_ALARM", "UNCERTAIN"]:
            final_risk_level = "NON_URGENT" if final_risk_level == "FALSE_ALARM" else final_risk_level
            final_risk_score = max(0.6, final_risk_score)
            final_reasoning = (
                f"Adjusted due to known medical conditions. {final_reasoning}"
            )

        suspicion_reason = None
        if translated_text:
            suspicion_reason = _translation_suspicion_reason(
                original_transcript or transcript,
                translated_text,
            )

        if suspicion_reason and final_risk_level == "NON_URGENT":
            original_snippet = _trim_for_reason(original_transcript or transcript)
            translated_snippet = _trim_for_reason(translated_text)
            final_risk_level = "UNCERTAIN"
            final_risk_score = min(max(final_risk_score, 0.5), 0.7)
            final_reasoning = (
                "Adjusted to UNCERTAIN due to suspicious translation quality "
                f"({suspicion_reason}). Source: '{original_snippet}'. "
                f"Translated: '{translated_snippet}'. {final_reasoning}"
            )

        if final_risk_score < 0.3 and final_risk_level in ["URGENT", "NON_URGENT"]:
            final_risk_level = "UNCERTAIN"
            final_reasoning = (
                f"Low confidence score adjusted to UNCERTAIN. {final_reasoning}"
            )

        return RiskAnalysis(
            risk_level=final_risk_level,
            risk_score=final_risk_score,
            reasoning=final_reasoning,
            keywords=list(set(analysis.keywords + keywords_found)),
            recommended_actions=analysis.recommended_actions,
        )

    @staticmethod
    def generate_summary(
        senior_name: str,
        risk_level: str,
        risk_score: float,
        reasoning: str,
        keywords: list[str],
    ) -> str:
        """Generate human-readable summary for operators."""
        emoji_map = {
            "URGENT": "🔴",
            "NON_URGENT": "🟠",
            "UNCERTAIN": "🟡",
            "FALSE_ALARM": "🟢",
        }
        emoji = emoji_map.get(risk_level, "⚪")
        risk_label = risk_level.replace("_", " ")

        summary_parts = [
            f"{emoji} {risk_label} ALERT",
            "",
            f"Senior: {senior_name}",
            f"Confidence: {risk_score:.0%}",
            "",
            "Assessment:",
            reasoning,
        ]

        if keywords:
            summary_parts.extend(["", f"Keywords: {', '.join(keywords)}"])

        return "\n".join(summary_parts)
