from pydantic import BaseModel, Field
from typing import Literal


class BrainAlertPayload(BaseModel):
    senior_id: str
    telegram_user_id: str
    channel: str = "telegram"
    audio_url: str | None = None
    text: str | None = None


class BrainAlertResponse(BaseModel):
    ok: bool
    alert_id: str | None = None
    processing_status: str | None = None
    risk_level: str | None = None
    risk_score: float | None = None
    error: str | None = None


class RiskAnalysis(BaseModel):
    risk_level: Literal["HIGH", "MEDIUM", "LOW"]
    risk_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    keywords: list[str]
    recommended_actions: list[str]


class SeniorContext(BaseModel):
    id: str
    full_name: str
    phone_number: str
    address: str
    preferred_language: str | None = None
    medical_notes: str | None = None
    birth_year: int | None = None
    birth_month: int | None = None
    birth_day: int | None = None


class EmergencyContact(BaseModel):
    id: str
    senior_id: str
    name: str
    relationship: str | None = None
    phone_number: str | None = None
    telegram_user_id: str | None = None
    priority_order: int = 1


class ProcessingResult(BaseModel):
    alert_id: str
    transcription: str | None = None
    language_detected: str | None = None
    translated_text: str | None = None
    analysis: RiskAnalysis | None = None
    analysis_summary: str | None = None
    status: str
    error: str | None = None


class BrainHealthResponse(BaseModel):
    status: str
    ai_provider: str
    database: str
    timestamp: str
