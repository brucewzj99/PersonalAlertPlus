TRANSLATION_SYSTEM_PROMPT = """You are a professional translator. Translate the given text from {source_language} to English. 
Provide only the translation, nothing else. The translation should be natural and accurate."""

TRANSLATION_USER_PROMPT = """Translate the following text to English:

{text}"""

RISK_CLASSIFICATION_SYSTEM_PROMPT = """You are an AI triage assistant for a senior emergency alert system.
Your role is to analyze incoming voice message transcripts and classify the urgency level.

Classify the alert into one of four levels:
- URGENT: Immediate emergency, life-threatening, severe injury (e.g., fall, chest pain, can't breathe, unconscious, bleeding)
- NON_URGENT: Needs follow-up but not an immediate life-threatening emergency
- UNCERTAIN: Insufficient clarity, conflicting details, or needs direct senior confirmation
- FALSE_ALARM: Accidental press, obvious test message, or clearly no assistance needed

Consider:
- Keywords indicating emergency (fall, pain, help, can't breathe, dizzy, weak, bleeding)
- Context from the message
- Senior's medical history (if provided) - conditions like hypertension, diabetes, mobility issues increase risk
- Language emotional tone (panic vs calm)

Output a JSON object with:
- risk_level: "URGENT", "NON_URGENT", "UNCERTAIN", or "FALSE_ALARM"
- risk_score: a float between 0.0 and 1.0
- reasoning: brief explanation of the classification
- keywords: array of relevant keywords found
- recommended_actions: array of suggested actions

Be conservative - when in doubt between categories, choose UNCERTAIN or NON_URGENT over FALSE_ALARM."""

RISK_CLASSIFICATION_USER_PROMPT = """Analyze this alert transcript:

Senior Name: {senior_name}
Medical Notes: {medical_notes}
Preferred Language: {preferred_language}

Transcript:
{transcript}

Original Language: {language}

Provide your risk classification as JSON."""

FALLBACK_CLASSIFICATION_PROMPT = """The transcription service failed. Based on the available information:

Senior Name: {senior_name}
Medical Notes: {medical_notes}

Text input: {text}

Please classify the risk level based on this text."""

EMERGENCY_KEYWORDS = [
    "fall", "fell", "fell down", "fallen",
    "can't breathe", "cannot breathe", "choking",
    "chest pain", "heart pain", "heart attack",
    "unconscious", "fainted", "faint",
    "bleeding", "bleed", "blood",
    "dizzy", "dizziness", "vertigo",
    "weak", "weakness", "numb",
    "help", "help me", "emergency",
    "pain", "hurt", "injured",
    "can't move", "cannot move", "paralyzed",
    "stroke", "seizure",
    "confused", "disoriented",
]


def detect_emergency_keywords(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text_lower:
            found.append(keyword)
    return found


def map_language_code(lang_code: str | None) -> str:
    mapping = {
        "en": "English",
        "zh": "Chinese",
        "ms": "Malay",
        "ta": "Tamil",
        "nan": "Hokkien",
        "yue": "Cantonese",
    }
    return mapping.get(lang_code or "en", "English")
