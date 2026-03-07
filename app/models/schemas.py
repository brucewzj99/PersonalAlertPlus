from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, field_validator

SINGAPORE_COUNTRY_CODE = "+65"
SINGAPORE_PHONE_DIGITS = 8


def _normalize_singapore_phone_number(value: str | None) -> str | None:
    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    digits_only = re.sub(r"\D", "", trimmed)
    local_digits = (
        digits_only[2:]
        if digits_only.startswith("65")
        and len(digits_only) == SINGAPORE_PHONE_DIGITS + 2
        else digits_only
    )

    if not local_digits.isdigit() or len(local_digits) != SINGAPORE_PHONE_DIGITS:
        raise ValueError("Phone number must contain exactly 8 digits")

    return f"{SINGAPORE_COUNTRY_CODE}{local_digits}"


class Senior(BaseModel):
    id: str
    full_name: str
    phone_number: str
    telegram_user_id: str | None = None
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
    alert_id: str | None = None
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


class FewShotExampleUpdate(BaseModel):
    transcript: str | None = None
    risk_level: str | None = None


class EmergencyContactInsert(BaseModel):
    senior_id: str
    name: str
    relationship: str | None = None
    phone_number: str | None = None
    telegram_user_id: str | None = None
    priority_order: int = 1
    notify_on_uncertain: bool = False

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        return _normalize_singapore_phone_number(value)


class EmergencyContactUpdate(BaseModel):
    name: str | None = None
    relationship: str | None = None
    phone_number: str | None = None
    telegram_user_id: str | None = None
    priority_order: int | None = None
    notify_on_uncertain: bool | None = None

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        return _normalize_singapore_phone_number(value)


class AlertUpdate(BaseModel):
    risk_level: str | None = None
    risk_score: float | None = None
    requires_operator: bool | None = None
    status: str | None = None
    ambulance_dispatched: bool | None = None
    family_called: bool | None = None
    is_attended: bool | None = None
    is_resolved: bool | None = None
    operator: str | None = None
    action_time: datetime | None = None
    operator_actions: list[dict[str, Any]] | None = None
