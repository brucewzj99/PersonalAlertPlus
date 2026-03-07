from pydantic import BaseModel


class Senior(BaseModel):
    id: str
    full_name: str
    phone_number: str
    telegram_user_id: str | None = None
    button_id: str | None = None
    address: str
    birth_year: int | None = None
    birth_month: int | None = None
    birth_day: int | None = None
    preferred_language: str | None = None
    medical_notes: str | None = None


class AlertInsert(BaseModel):
    senior_id: str
    channel: str = "telegram"
    audio_url: str | None = None
    transcription: str | None = None


class BackendAlertPayload(BaseModel):
    senior_id: str
    telegram_user_id: str
    channel: str = "telegram"
    audio_url: str | None = None
    """Optional: voice recording as base64 (e.g. from Telegram). Used for Groq transcription when present."""
    audio_base64: str | None = None
    text: str | None = None


class FewShotExample(BaseModel):
    id: str | None = None
    transcript: str
    risk_level: str
    created_at: str | None = None


class AlertUpdate(BaseModel):
    risk_level: str | None = None
    risk_score: float | None = None
    requires_operator: bool | None = None
    status: str | None = None
    ambulance_dispatched: bool | None = None
    family_called: bool | None = None
    is_attended: bool | None = None
    is_resolved: bool | None = None
    operator_notes: str | None = None
