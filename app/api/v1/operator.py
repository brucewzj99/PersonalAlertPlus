import re
import logging
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query
from postgrest.exceptions import APIError
from pydantic import BaseModel
from telegram import Bot

from app.models.schemas import (
    AlertUpdate,
    EmergencyContactInsert,
    EmergencyContactUpdate,
    FewShotExample,
    FewShotExampleUpdate,
)
from app.config import get_settings
from app.services.database import DatabaseService

router = APIRouter(prefix="/api/v1/operator", tags=["operator"])
db = DatabaseService()
logger = logging.getLogger(__name__)

OPERATOR_ACTION_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "family": "We have contacted your family member to keep them informed and support you.",
        "ambulance": "An ambulance has been dispatched and is on the way to your location.",
        "both": "An ambulance has been dispatched and your family member has been contacted to support you.",
    },
    "zh": {
        "family": "我们已联系您的家属，通知他们您的情况并协助您。",
        "ambulance": "救护车已派出，正在前往您所在的位置。",
        "both": "救护车已派出，同时我们已联系您的家属来协助您。",
    },
    "ms": {
        "family": "Kami telah menghubungi ahli keluarga anda untuk memaklumkan keadaan anda dan membantu anda.",
        "ambulance": "Ambulans telah dihantar dan sedang menuju ke lokasi anda.",
        "both": "Ambulans telah dihantar dan ahli keluarga anda telah dihubungi untuk membantu anda.",
    },
    "ta": {
        "family": "உங்கள் நிலை பற்றி தெரிவிக்கவும் உங்களுக்கு உதவவும் உங்கள் குடும்பத்தினருடன் தொடர்பு கொண்டுள்ளோம்.",
        "ambulance": "ஆம்புலன்ஸ் அனுப்பப்பட்டுள்ளது, அது உங்கள் இருப்பிடத்திற்கு வந்து கொண்டிருக்கிறது.",
        "both": "ஆம்புலன்ஸ் அனுப்பப்பட்டுள்ளது, மேலும் உங்களுக்கு உதவ உங்கள் குடும்பத்தினருக்கும் தகவல் அளிக்கப்பட்டுள்ளது.",
    },
    "nan": {
        "family": "阮已经联络你的家人，通知你的情况来协助你。",
        "ambulance": "救护车已经派出，正在赶去你的所在位置。",
        "both": "救护车已经派出，阮也已经联络你的家人来协助你。",
    },
    "yue": {
        "family": "我哋已经联络你嘅家人，通知佢哋你嘅情况并协助你。",
        "ambulance": "救护车已经派出，正赶往你而家嘅位置。",
        "both": "救护车已经派出，同时我哋已经联络你嘅家人去协助你。",
    },
}


def _operator_action_key(ambulance: bool, family: bool) -> str | None:
    if ambulance and family:
        return "both"
    if ambulance:
        return "ambulance"
    if family:
        return "family"
    return None


def _operator_action_audio_path(language: str, action_key: str) -> Path:
    audio_filename_map = {
        "family": "operator_family_called.mp3",
        "ambulance": "operator_ambulance_dispatched.mp3",
        "both": "operator_family_and_ambulance.mp3",
    }
    filename = audio_filename_map[action_key]
    return Path(__file__).resolve().parents[3] / "assets" / "audio" / language / filename


async def _notify_senior_operator_action(
    senior_id: str,
    ambulance_dispatched_now: bool,
    family_called_now: bool,
) -> None:
    action_key = _operator_action_key(ambulance_dispatched_now, family_called_now)
    if action_key is None:
        return

    senior_response = (
        db.client.table("seniors")
        .select("telegram_user_id, preferred_language")
        .eq("id", senior_id)
        .limit(1)
        .execute()
    )
    senior_rows = _ensure_dict_rows(senior_response.data)
    if not senior_rows:
        return

    senior = senior_rows[0]
    telegram_user_id = senior.get("telegram_user_id")
    if not telegram_user_id:
        return

    preferred_language = str(senior.get("preferred_language") or "en").lower()
    language = preferred_language if preferred_language in OPERATOR_ACTION_MESSAGES else "en"
    text = OPERATOR_ACTION_MESSAGES[language][action_key]

    bot = Bot(token=get_settings().telegram_bot_token)
    await bot.send_message(chat_id=str(telegram_user_id), text=f"✅ {text}")

    audio_path = _operator_action_audio_path(language, action_key)
    if audio_path.exists():
        with open(audio_path, "rb") as audio_file:
            await bot.send_voice(
                chat_id=str(telegram_user_id),
                voice=audio_file,
                caption=text,
            )


class FewShotExampleCreate(BaseModel):
    transcript: str
    risk_level: str


class PromptSettingUpdate(BaseModel):
    value: str


def _ensure_dict_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _normalize_alert_update(update_payload: dict[str, Any]) -> dict[str, Any]:
    risk_level = update_payload.get("risk_level")
    if risk_level == "FALSE_ALARM":
        update_payload.setdefault("status", "closed")
        update_payload.setdefault("is_resolved", True)
        update_payload.setdefault("requires_operator", False)
    elif risk_level == "UNCERTAIN":
        update_payload.setdefault("status", "pending_confirmation")
        update_payload.setdefault("is_resolved", False)
        update_payload.setdefault("requires_operator", False)
    elif risk_level in {"URGENT", "NON_URGENT"}:
        update_payload.setdefault("status", "escalated")
        update_payload.setdefault("is_resolved", False)
        update_payload.setdefault("requires_operator", True)

    if (update_payload.get("status") or "").lower() == "closed":
        update_payload.setdefault("is_resolved", True)

    return update_payload


def _is_missing_column_error(exc: Exception, column_name: str) -> bool:
    if not isinstance(exc, APIError):
        return False
    message = str(exc)
    return "does not exist" in message and column_name in message


def _is_missing_table_error(exc: Exception, table_name: str) -> bool:
    if not isinstance(exc, APIError):
        return False
    message = str(exc)
    return "does not exist" in message and table_name in message


def _extract_missing_column(exc: Exception, table_name: str) -> str | None:
    if not isinstance(exc, APIError):
        return None
    pattern = rf"column\s+{re.escape(table_name)}\.(\w+)\s+does not exist"
    match = re.search(pattern, str(exc), flags=re.IGNORECASE)
    return match.group(1) if match else None


def _update_alert_with_fallback(alert_id: str, updates: dict[str, Any]):
    payload = dict(updates)
    while True:
        if not payload:
            return (
                db.client.table("alerts")
                .select("*")
                .eq("id", alert_id)
                .limit(1)
                .execute()
            )
        try:
            return db.client.table("alerts").update(payload).eq("id", alert_id).execute()
        except Exception as exc:
            missing = _extract_missing_column(exc, "alerts")
            if missing and missing in payload:
                payload.pop(missing, None)
                continue
            raise


def _insert_contact_with_fallback(row: dict[str, Any]):
    payload = dict(row)
    while True:
        try:
            return db.client.table("emergency_contacts").insert(payload).execute()
        except Exception as exc:
            missing = _extract_missing_column(exc, "emergency_contacts")
            if missing and missing in payload:
                payload.pop(missing, None)
                continue
            raise


def _update_contact_with_fallback(contact_id: str, updates: dict[str, Any]):
    payload = dict(updates)
    while True:
        if not payload:
            return (
                db.client.table("emergency_contacts")
                .select("*")
                .eq("id", contact_id)
                .limit(1)
                .execute()
            )
        try:
            return (
                db.client.table("emergency_contacts")
                .update(payload)
                .eq("id", contact_id)
                .execute()
            )
        except Exception as exc:
            missing = _extract_missing_column(exc, "emergency_contacts")
            if missing and missing in payload:
                payload.pop(missing, None)
                continue
            raise


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_closed: bool = Query(True),
) -> list[dict[str, Any]]:
    """Fetch alerts sorted by priority and time for the operator dashboard."""
    try:
        response = (
            db.client.table("alerts")
            .select("*, seniors(id, full_name, phone_number, address, preferred_language)")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        alerts = _ensure_dict_rows(response.data)
    except Exception as exc:
        if _is_missing_table_error(exc, "alerts"):
            alerts = []
        else:
            raise

    if not include_closed:
        alerts = [
            alert
            for alert in alerts
            if not (
                alert.get("is_resolved") is True
                or (alert.get("status") or "").lower() == "closed"
            )
        ]

    priority_order = {
        "URGENT": 4,
        "NON_URGENT": 3,
        "UNCERTAIN": 2,
        "FALSE_ALARM": 1,
        None: 0,
    }

    return sorted(
        alerts,
        key=lambda row: (
            priority_order.get(cast(str | None, row.get("risk_level")), 0),
            row.get("created_at") or "",
        ),
        reverse=True,
    )


@router.patch("/alerts/{alert_id}/override")
async def override_alert(
    alert_id: str,
    update: AlertUpdate,
    save_as_example: bool = Query(False),
) -> dict[str, Any]:
    """Override an alert's risk level and optionally save as a few-shot example."""
    current = (
        db.client.table("alerts")
        .select("id, senior_id, transcription, ambulance_dispatched, family_called")
        .eq("id", alert_id)
        .limit(1)
        .execute()
    )
    current_rows = _ensure_dict_rows(current.data)
    if not current_rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    current_row = current_rows[0]
    transcript = current_row.get("transcription")

    update_payload = _normalize_alert_update(update.model_dump(exclude_none=True))
    updated = _update_alert_with_fallback(alert_id, update_payload)
    updated_rows = _ensure_dict_rows(updated.data)
    if not updated_rows:
        raise HTTPException(status_code=404, detail="Alert not found")

    if save_as_example and transcript and update.risk_level:
        db.create_few_shot_example(
            FewShotExample(transcript=str(transcript), risk_level=update.risk_level)
        )

    updated_row = updated_rows[0]

    old_ambulance = bool(current_row.get("ambulance_dispatched"))
    old_family = bool(current_row.get("family_called"))
    new_ambulance = bool(updated_row.get("ambulance_dispatched"))
    new_family = bool(updated_row.get("family_called"))

    ambulance_dispatched_now = (not old_ambulance) and new_ambulance
    family_called_now = (not old_family) and new_family

    senior_id = current_row.get("senior_id")
    if isinstance(senior_id, str) and (ambulance_dispatched_now or family_called_now):
        try:
            await _notify_senior_operator_action(
                senior_id=senior_id,
                ambulance_dispatched_now=ambulance_dispatched_now,
                family_called_now=family_called_now,
            )
        except Exception as exc:
            logger.warning("Failed to send operator action notification to senior: %s", exc)

    return updated_row


@router.get("/alerts/{alert_id}/conversation-replies")
async def get_conversation_replies(alert_id: str) -> list[dict[str, Any]]:
    response = (
        db.client.table("ai_actions")
        .select("created_at, details")
        .eq("alert_id", alert_id)
        .eq("action_type", "senior_conversation_reply")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    rows = _ensure_dict_rows(response.data)

    normalized: list[dict[str, Any]] = []
    for row in rows:
        details = row.get("details")
        details_dict = details if isinstance(details, dict) else {}
        normalized.append(
            {
                "created_at": row.get("created_at"),
                "english_text": details_dict.get("message_en"),
                "original_text": details_dict.get("message_original"),
                "source_language": details_dict.get("source_language"),
                "translated": bool(details_dict.get("translated")),
                "has_voice": bool(details_dict.get("has_voice")),
                "audio_url": details_dict.get("audio_url"),
            }
        )
    return normalized


@router.get("/few-shot-examples")
async def get_examples(limit: int = Query(20, ge=1, le=200)) -> list[FewShotExample]:
    return db.get_few_shot_examples(limit=limit)


@router.post("/few-shot-examples", response_model=FewShotExample)
async def create_example(payload: FewShotExampleCreate) -> FewShotExample:
    example = FewShotExample(
        transcript=payload.transcript.strip(),
        risk_level=payload.risk_level,
    )
    return db.create_few_shot_example(example)


@router.delete("/few-shot-examples/{example_id}")
async def delete_example(example_id: str) -> dict[str, bool]:
    db.client.table("few_shot_examples").delete().eq("id", example_id).execute()
    return {"ok": True}


@router.patch("/few-shot-examples/{example_id}")
async def update_example(
    example_id: str,
    payload: FewShotExampleUpdate,
) -> dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    response = (
        db.client.table("few_shot_examples")
        .update(updates)
        .eq("id", example_id)
        .execute()
    )
    rows = _ensure_dict_rows(response.data)
    if not rows:
        raise HTTPException(status_code=404, detail="Few-shot example not found")
    return rows[0]


@router.get("/seniors/overview")
async def get_seniors_overview() -> list[dict[str, Any]]:
    try:
        seniors_response = (
            db.client.table("seniors")
            .select(
                "id, full_name, phone_number, address, preferred_language, medical_notes, created_at"
            )
            .order("full_name")
            .execute()
        )
    except Exception as exc:
        if _is_missing_column_error(exc, "seniors.medical_notes"):
            seniors_response = (
                db.client.table("seniors")
                .select("id, full_name, phone_number, address, preferred_language, created_at")
                .order("full_name")
                .execute()
            )
        elif _is_missing_table_error(exc, "seniors"):
            return []
        else:
            raise
    alerts_rows: list[dict[str, Any]] = []
    try:
        alerts_response = (
            db.client.table("alerts")
            .select("id, senior_id, created_at, status, risk_level, requires_operator, is_resolved")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        alerts_rows = _ensure_dict_rows(alerts_response.data)
    except Exception as exc:
        if _is_missing_column_error(exc, "alerts.is_resolved"):
            alerts_response = (
                db.client.table("alerts")
                .select("id, senior_id, created_at, status, risk_level, requires_operator")
                .order("created_at", desc=True)
                .limit(500)
                .execute()
            )
            alerts_rows = _ensure_dict_rows(alerts_response.data)
        elif _is_missing_table_error(exc, "alerts"):
            alerts_rows = []
        else:
            raise

    seniors_rows = _ensure_dict_rows(seniors_response.data)

    latest_alert_by_senior: dict[str, dict[str, Any]] = {}
    open_count_by_senior: dict[str, int] = {}
    total_count_by_senior: dict[str, int] = {}

    for alert in alerts_rows:
        senior_id = cast(str | None, alert.get("senior_id"))
        if not senior_id:
            continue

        if senior_id not in latest_alert_by_senior:
            latest_alert_by_senior[senior_id] = alert

        total_count_by_senior[senior_id] = total_count_by_senior.get(senior_id, 0) + 1

        is_closed = (
            alert.get("is_resolved") is True
            or (str(alert.get("status") or "")).lower() == "closed"
        )
        if not is_closed:
            open_count_by_senior[senior_id] = open_count_by_senior.get(senior_id, 0) + 1

    rows: list[dict[str, Any]] = []
    for senior in seniors_rows:
        senior_id = cast(str | None, senior.get("id"))
        rows.append(
            {
                **senior,
                "open_cases": open_count_by_senior.get(senior_id or "", 0),
                "total_cases": total_count_by_senior.get(senior_id or "", 0),
                "latest_alert": latest_alert_by_senior.get(senior_id or ""),
            }
        )

    return rows


@router.get("/seniors/{senior_id}/emergency-contacts")
async def get_emergency_contacts(senior_id: str) -> list[dict[str, Any]]:
    response = (
        db.client.table("emergency_contacts")
        .select("*")
        .eq("senior_id", senior_id)
        .order("priority_order")
        .execute()
    )
    return _ensure_dict_rows(response.data)


@router.post("/seniors/{senior_id}/emergency-contacts")
async def create_emergency_contact(
    senior_id: str,
    payload: EmergencyContactInsert,
) -> dict[str, Any]:
    row = payload.model_dump()
    row["senior_id"] = senior_id
    response = _insert_contact_with_fallback(row)
    rows = _ensure_dict_rows(response.data)
    if not rows:
        raise HTTPException(status_code=400, detail="Failed to create emergency contact")
    return rows[0]


@router.patch("/emergency-contacts/{contact_id}")
async def update_emergency_contact(
    contact_id: str,
    payload: EmergencyContactUpdate,
) -> dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    response = _update_contact_with_fallback(contact_id, updates)
    rows = _ensure_dict_rows(response.data)
    if not rows:
        raise HTTPException(status_code=404, detail="Emergency contact not found")
    return rows[0]


@router.delete("/emergency-contacts/{contact_id}")
async def delete_emergency_contact(contact_id: str) -> dict[str, bool]:
    db.client.table("emergency_contacts").delete().eq("id", contact_id).execute()
    return {"ok": True}


@router.get("/settings/risk-prompt")
async def get_risk_prompt_setting() -> dict[str, str]:
    value = db.get_prompt_setting(
        key="risk_classification_system_prompt",
        default_value=db.default_risk_prompt_template,
    )
    return {"key": "risk_classification_system_prompt", "value": value}


@router.put("/settings/risk-prompt")
async def update_risk_prompt_setting(payload: PromptSettingUpdate) -> dict[str, str]:
    value = payload.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    try:
        saved_value = db.set_prompt_setting(
            key="risk_classification_system_prompt",
            value=value,
        )
    except Exception as exc:
        if _is_missing_table_error(exc, "prompt_settings"):
            raise HTTPException(
                status_code=400,
                detail="Missing prompt_settings table. Run latest database migration first.",
            ) from exc
        raise

    return {"key": "risk_classification_system_prompt", "value": saved_value}
