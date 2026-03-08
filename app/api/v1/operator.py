import re
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
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
from app.brain.providers.openai_compatible import OpenAICompatibleClient
from app.services.database import DatabaseService

router = APIRouter(prefix="/api/v1/operator", tags=["operator"])
db = DatabaseService()
logger = logging.getLogger(__name__)

ACTION_RECOMMENDATION_SYSTEM_PROMPT = """You are an AI assistant helping an emergency operator decide response actions.
Choose only from the enabled available choices.

Guidelines:
- Prioritize senior safety and urgency.
- Use current case details first, then historical alerts for context.
- Keep rationale concise and actionable.
- Do not invent choices that are not in available_choices.
- Allowed action keys are: senior_activity_centre_staff, careline_staff, community_responder, police, scdf, call.

Return strict JSON with this schema:
{
  "recommended_actions": ["choice_key_1", "choice_key_2"],
  "rationale": "Short explanation for operator.",
  "confidence": 0.0,
  "context_alert_ids": ["historical_alert_id_1"]
}

Rules for confidence:
- between 0.0 and 1.0
- higher when evidence is explicit and consistent
- lower when details are unclear or conflicting
"""

ALLOWED_RECOMMENDATION_ACTIONS = {
    "senior_activity_centre_staff",
    "careline_staff",
    "community_responder",
    "police",
    "scdf",
    "call",
}

OPERATOR_ACTION_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "family": "We have contacted your family member to keep them informed and support you.",
        "ambulance": "An ambulance has been dispatched and is on the way to your location.",
        "both": "An ambulance has been dispatched and your family member has been contacted to support you.",
        "attended": "Our team has attended to your case and is continuing to monitor your situation.",
    },
    "zh": {
        "family": "我们已联系您的家属，通知他们您的情况并协助您。",
        "ambulance": "救护车已派出，正在前往您所在的位置。",
        "both": "救护车已派出，同时我们已联系您的家属来协助您。",
        "attended": "我们的团队已接手您的个案，并会持续关注您的情况。",
    },
    "ms": {
        "family": "Kami telah menghubungi ahli keluarga anda untuk memaklumkan keadaan anda dan membantu anda.",
        "ambulance": "Ambulans telah dihantar dan sedang menuju ke lokasi anda.",
        "both": "Ambulans telah dihantar dan ahli keluarga anda telah dihubungi untuk membantu anda.",
        "attended": "Pasukan kami telah menangani kes anda dan akan terus memantau keadaan anda.",
    },
    "ta": {
        "family": "உங்கள் நிலை பற்றி தெரிவிக்கவும் உங்களுக்கு உதவவும் உங்கள் குடும்பத்தினருடன் தொடர்பு கொண்டுள்ளோம்.",
        "ambulance": "ஆம்புலன்ஸ் அனுப்பப்பட்டுள்ளது, அது உங்கள் இருப்பிடத்திற்கு வந்து கொண்டிருக்கிறது.",
        "both": "ஆம்புலன்ஸ் அனுப்பப்பட்டுள்ளது, மேலும் உங்களுக்கு உதவ உங்கள் குடும்பத்தினருக்கும் தகவல் அளிக்கப்பட்டுள்ளது.",
        "attended": "எங்கள் குழு உங்கள் நிலையை கவனத்தில் கொண்டு வழக்கை தொடர்ந்து கையாளுகிறது.",
    },
    "nan": {
        "family": "阮已经联络你的家人，通知你的情况来协助你。",
        "ambulance": "救护车已经派出，正在赶去你的所在位置。",
        "both": "救护车已经派出，阮也已经联络你的家人来协助你。",
        "attended": "阮的团队已经接手处理你的案件，请放心。",
    },
    "yue": {
        "family": "我哋已经联络你嘅家人，通知佢哋你嘅情况并协助你。",
        "ambulance": "救护车已经派出，正赶往你而家嘅位置。",
        "both": "救护车已经派出，同时我哋已经联络你嘅家人去协助你。",
        "attended": "我哋嘅团队已经接手跟进你嘅个案，请放心。",
    },
}

OPERATOR_ACTION_AUDIO_CANDIDATES: dict[str, list[str]] = {
    "family": ["operator_family_called.mp3"],
    "ambulance": ["operator_ambulance_dispatched.mp3"],
    "both": ["operator_family_and_ambulance.mp3"],
    "attended": ["operator_case_attended.mp3"],
}


def _operator_action_key(ambulance: bool, family: bool, attended: bool) -> str | None:
    if ambulance and family:
        return "both"
    if ambulance:
        return "ambulance"
    if family:
        return "family"
    if attended:
        return "attended"
    return None


def _operator_action_audio_path(language: str, action_key: str) -> Path:
    audio_dir = Path(__file__).resolve().parents[3] / "assets" / "audio" / language
    for filename in OPERATOR_ACTION_AUDIO_CANDIDATES.get(action_key, []):
        candidate = audio_dir / filename
        if candidate.exists():
            return candidate
    return audio_dir / OPERATOR_ACTION_AUDIO_CANDIDATES[action_key][0]


async def _notify_senior_operator_action(
    senior_id: str,
    ambulance_dispatched_now: bool,
    family_called_now: bool,
    case_attended_now: bool,
) -> None:
    action_key = _operator_action_key(
        ambulance_dispatched_now,
        family_called_now,
        case_attended_now,
    )
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
    language = (
        preferred_language if preferred_language in OPERATOR_ACTION_MESSAGES else "en"
    )
    text = OPERATOR_ACTION_MESSAGES[language][action_key]

    bot = Bot(token=get_settings().telegram_bot_token)
    audio_path = _operator_action_audio_path(language, action_key)
    if audio_path.exists():
        with open(audio_path, "rb") as audio_file:
            await bot.send_voice(
                chat_id=str(telegram_user_id),
                voice=audio_file,
                caption=f"✅ {text}",
            )
    else:
        logger.warning(
            "Missing operator action audio for language '%s', action '%s' (expected at %s)",
            language,
            action_key,
            audio_path,
        )
        await bot.send_message(chat_id=str(telegram_user_id), text=f"✅ {text}")


class FewShotExampleCreate(BaseModel):
    transcript: str
    risk_level: str


class PromptSettingUpdate(BaseModel):
    value: str


class ActionChoice(BaseModel):
    action_key: str
    label: str
    enabled: bool = True
    metadata: dict[str, Any] | None = None


class ActionRecommendationRequest(BaseModel):
    available_choices: list[ActionChoice]


class ActionRecommendationResponse(BaseModel):
    recommended_actions: list[str]
    recommended_labels: list[str]
    rationale: str
    confidence: float
    context_alert_ids: list[str]
    based_on_previous_alerts: int
    fallback_used: bool


def _ensure_dict_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _normalize_action_choice_key(value: str) -> str:
    normalized = re.sub(r"[\s\-]+", "_", (value or "").strip().lower())
    aliases = {
        "dispatch_ambulance": "scdf",
        "dispatchambulance": "scdf",
        "ambulance": "scdf",
        "call_family": "call",
        "family": "call",
        "family_called": "call",
        "callfamily": "call",
    }
    return aliases.get(normalized, normalized)


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(1.0, max(0.0, parsed))


def _fallback_action_recommendation(
    current_alert: dict[str, Any],
    enabled_choices: list[dict[str, Any]],
) -> dict[str, Any]:
    risk_level = str(current_alert.get("risk_level") or "").upper()
    enabled_keys = {
        _normalize_action_choice_key(str(choice.get("action_key") or ""))
        for choice in enabled_choices
    }

    recommended_actions: list[str] = []
    if risk_level == "URGENT":
        if "scdf" in enabled_keys:
            recommended_actions.append("scdf")
        if "police" in enabled_keys:
            recommended_actions.append("police")
        if "call" in enabled_keys:
            recommended_actions.append("call")
    elif risk_level in {"NON_URGENT", "UNCERTAIN"}:
        if "careline_staff" in enabled_keys:
            recommended_actions.append("careline_staff")
        elif "senior_activity_centre_staff" in enabled_keys:
            recommended_actions.append("senior_activity_centre_staff")
        if "call" in enabled_keys:
            recommended_actions.append("call")
    else:
        if "call" in enabled_keys:
            recommended_actions.append("call")

    recommended_actions = [
        action for action in recommended_actions if action in ALLOWED_RECOMMENDATION_ACTIONS
    ]

    if not recommended_actions and enabled_choices:
        first_choice = enabled_choices[0]
        recommended_actions = [
            _normalize_action_choice_key(str(first_choice.get("action_key") or ""))
        ]

    return {
        "recommended_actions": [key for key in recommended_actions if key],
        "rationale": (
            "Fallback recommendation based on current risk level and enabled actions."
        ),
        "confidence": 0.6 if risk_level in {"URGENT", "NON_URGENT"} else 0.45,
        "context_alert_ids": [],
        "fallback_used": True,
    }


def _choice_labels_by_key(
    choices: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for choice in choices:
        key = _normalize_action_choice_key(str(choice.get("action_key") or ""))
        if not key or key not in ALLOWED_RECOMMENDATION_ACTIONS:
            continue
        label = str(choice.get("label") or "").strip() or key.replace("_", " ").title()
        mapping[key] = label
    return mapping


def _log_action_recommendation(
    alert_id: str,
    details: dict[str, Any],
    provider: str,
    action_status: str,
) -> None:
    try:
        db.client.table("ai_actions").insert(
            {
                "alert_id": alert_id,
                "action_type": "operator_action_recommendation",
                "action_status": action_status,
                "details": details,
                "provider": provider,
            }
        ).execute()
    except Exception as exc:
        logger.warning("Failed to log action recommendation in ai_actions: %s", exc)

    try:
        db.client.table("operator_action_recommendations").insert(
            {
                "case_id": alert_id,
                "model": provider,
                "available_choices": details.get("available_choices") or [],
                "recommended_actions": details.get("recommended_actions") or [],
                "recommended_labels": details.get("recommended_labels") or [],
                "rationale": details.get("rationale") or "",
                "confidence": details.get("confidence"),
                "context_alert_ids": details.get("context_alert_ids") or [],
                "raw_response": details.get("raw_response") or {},
            }
        ).execute()
    except Exception as exc:
        if _is_missing_table_error(exc, "operator_action_recommendations"):
            return
        logger.warning("Failed to log recommendation in dedicated table: %s", exc)


def _normalize_alert_update(update_payload: dict[str, Any]) -> dict[str, Any]:
    raw_status = str(update_payload.get("status") or "").strip().lower()
    if raw_status in {"case closed", "case_closed"}:
        update_payload["status"] = "closed"

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

    if update_payload.get("is_resolved") is True:
        update_payload.setdefault("status", "closed")

    return update_payload


def _normalize_action_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    normalized = re.sub(r"[\s\-]+", "_", raw)
    aliases = {
        "ambulance": "dispatch_ambulance",
        "ambulance_dispatched": "dispatch_ambulance",
        "dispatchambulance": "dispatch_ambulance",
        "family": "call_family",
        "family_called": "call_family",
        "callfamily": "call_family",
        "attended": "mark_attended",
        "is_attended": "mark_attended",
    }
    return aliases.get(normalized, normalized)


def _serialize_action_time(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).isoformat()


def _collect_operator_actions(update: AlertUpdate) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    raw_events = update.operator_actions or []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        action_name = _normalize_action_name(
            event.get("actions_taken") or event.get("action")
        )
        if not action_name:
            continue
        payload = event.get("action_payload")
        if not isinstance(payload, dict):
            payload = {}

        events.append(
            {
                "actions_taken": action_name,
                "action_payload": payload,
                "action_time": _serialize_action_time(
                    event.get("action_time") or update.action_time
                ),
            }
        )

    if update.ambulance_dispatched is True:
        events.append(
            {
                "actions_taken": "dispatch_ambulance",
                "action_payload": {},
                "action_time": _serialize_action_time(update.action_time),
            }
        )
    if update.family_called is True:
        events.append(
            {
                "actions_taken": "call_family",
                "action_payload": {},
                "action_time": _serialize_action_time(update.action_time),
            }
        )
    if update.is_attended is True:
        events.append(
            {
                "actions_taken": "mark_attended",
                "action_payload": {},
                "action_time": _serialize_action_time(update.action_time),
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        key = (
            f"{event['actions_taken']}|{event['action_time']}|{event['action_payload']}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


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


def _insert_operator_actions(
    alert_id: str,
    operator_name: str,
    events: list[dict[str, Any]],
) -> None:
    if not events:
        return

    rows = [
        {
            "case_id": alert_id,
            "operator": operator_name,
            "actions_taken": event["actions_taken"],
            "action_payload": event.get("action_payload") or {},
            "action_time": event["action_time"],
        }
        for event in events
    ]

    try:
        db.client.table("operator_actions").insert(rows).execute()
    except Exception as exc:
        if _is_missing_table_error(exc, "operator_actions"):
            logger.warning(
                "operator_actions table missing. Run DB migration before action logging."
            )
            return
        raise


def _attach_operator_action_state(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not alerts:
        return alerts

    for alert in alerts:
        alert["ambulance_dispatched"] = False
        alert["family_called"] = False
        alert["is_attended"] = False
        alert["dispatch_ambulance_at"] = None
        alert["family_called_at"] = None
        alert["operator_actions"] = []

    alert_ids = [str(alert.get("id") or "") for alert in alerts if alert.get("id")]
    if not alert_ids:
        return alerts

    try:
        response = (
            db.client.table("operator_actions")
            .select(
                "case_id, operator, actions_taken, action_payload, action_time, created_at"
            )
            .in_("case_id", alert_ids)
            .order("action_time", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as exc:
        if _is_missing_table_error(exc, "operator_actions"):
            return alerts
        raise

    action_rows = _ensure_dict_rows(response.data)
    actions_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in action_rows:
        case_id = str(row.get("case_id") or "")
        if not case_id:
            continue
        actions_by_case.setdefault(case_id, []).append(row)

    for alert in alerts:
        case_id = str(alert.get("id") or "")
        case_actions = actions_by_case.get(case_id, [])
        alert["operator_actions"] = case_actions

        for action in case_actions:
            action_name = _normalize_action_name(action.get("actions_taken"))
            if action_name == "dispatch_ambulance":
                alert["ambulance_dispatched"] = True
                if alert.get("dispatch_ambulance_at") is None:
                    alert["dispatch_ambulance_at"] = action.get("action_time")
            elif action_name == "call_family":
                alert["family_called"] = True
                if alert.get("family_called_at") is None:
                    alert["family_called_at"] = action.get("action_time")
            elif action_name == "mark_attended":
                alert["is_attended"] = True

    return alerts


def _attach_latest_ai_recommendation(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not alerts:
        return alerts

    for alert in alerts:
        alert["ai_recommendation"] = None

    alert_ids = [str(alert.get("id") or "") for alert in alerts if alert.get("id")]
    if not alert_ids:
        return alerts

    try:
        response = (
            db.client.table("operator_action_recommendations")
            .select(
                "case_id, recommended_actions, recommended_labels, rationale, confidence, context_alert_ids, created_at"
            )
            .in_("case_id", alert_ids)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as exc:
        if _is_missing_table_error(exc, "operator_action_recommendations"):
            return alerts
        raise

    rows = _ensure_dict_rows(response.data)
    by_case: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "")
        if not case_id or case_id in by_case:
            continue
        by_case[case_id] = row

    for alert in alerts:
        case_id = str(alert.get("id") or "")
        if case_id in by_case:
            recommendation = dict(by_case[case_id])
            raw_actions = recommendation.get("recommended_actions") or []
            filtered_actions = [
                _normalize_action_choice_key(str(item))
                for item in raw_actions
                if _normalize_action_choice_key(str(item)) in ALLOWED_RECOMMENDATION_ACTIONS
            ]
            recommendation["recommended_actions"] = filtered_actions
            alert["ai_recommendation"] = recommendation

    return alerts


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
            return (
                db.client.table("alerts").update(payload).eq("id", alert_id).execute()
            )
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
            .select(
                "*, seniors(id, full_name, phone_number, address, preferred_language, birth_year, birth_month, birth_day, sip_url)"
            )
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        alerts = _ensure_dict_rows(response.data)
    except Exception as exc:
        if _is_missing_column_error(exc, "seniors.birth_year") or _is_missing_column_error(exc, "seniors.sip_url"):
            response = (
                db.client.table("alerts")
                .select(
                    "*, seniors(id, full_name, phone_number, address, preferred_language, sip_url)"
                )
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            alerts = _ensure_dict_rows(response.data)
        elif _is_missing_table_error(exc, "alerts"):
            alerts = []
        else:
            raise

    alerts = _attach_operator_action_state(alerts)
    alerts = _attach_latest_ai_recommendation(alerts)

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
        .select("id, senior_id, transcription, resolved_by")
        .eq("id", alert_id)
        .limit(1)
        .execute()
    )
    current_rows = _ensure_dict_rows(current.data)
    if not current_rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    current_row = current_rows[0]
    transcript = current_row.get("transcription")

    raw_update_payload = update.model_dump(exclude_unset=True)
    update_payload = _normalize_alert_update(
        {
            key: value
            for key, value in raw_update_payload.items()
            if key
            not in {
                "operator",
                "action_time",
                "operator_actions",
                "ambulance_dispatched",
                "family_called",
                "is_attended",
            }
        }
    )

    operator_name = (
        update.operator
        or cast(str | None, current_row.get("resolved_by"))
        or "Operator 1"
    )
    update_payload["resolved_by"] = operator_name

    action_events = _collect_operator_actions(update)

    updated = _update_alert_with_fallback(alert_id, update_payload)
    updated_rows = _ensure_dict_rows(updated.data)
    if not updated_rows:
        raise HTTPException(status_code=404, detail="Alert not found")

    _insert_operator_actions(alert_id, operator_name, action_events)

    if save_as_example and transcript and update.risk_level:
        db.create_few_shot_example(
            FewShotExample(transcript=str(transcript), risk_level=update.risk_level)
        )

    updated_row = updated_rows[0]
    updated_row = _attach_operator_action_state([updated_row])[0]
    updated_row = _attach_latest_ai_recommendation([updated_row])[0]

    action_names = {
        _normalize_action_name(event.get("actions_taken")) for event in action_events
    }
    ambulance_dispatched_now = "dispatch_ambulance" in action_names
    family_called_now = "call_family" in action_names
    case_attended_now = "mark_attended" in action_names

    senior_id = current_row.get("senior_id")
    if isinstance(senior_id, str) and (
        ambulance_dispatched_now or family_called_now or case_attended_now
    ):
        try:
            await _notify_senior_operator_action(
                senior_id=senior_id,
                ambulance_dispatched_now=ambulance_dispatched_now,
                family_called_now=family_called_now,
                case_attended_now=case_attended_now,
            )
        except Exception as exc:
            logger.warning(
                "Failed to send operator action notification to senior: %s", exc
            )

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


@router.get("/alerts/{alert_id}/ai-actions")
async def get_ai_actions(alert_id: str) -> list[dict[str, Any]]:
    response = (
        db.client.table("ai_actions")
        .select(
            "id, action_type, action_status, details, provider, attempt_count, external_ref, error_message, created_at"
        )
        .eq("alert_id", alert_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    return _ensure_dict_rows(response.data)


@router.post(
    "/alerts/{alert_id}/recommend-actions",
    response_model=ActionRecommendationResponse,
)
async def recommend_actions_for_case(
    alert_id: str,
    payload: ActionRecommendationRequest,
) -> ActionRecommendationResponse:
    try:
        existing_response = (
            db.client.table("operator_action_recommendations")
            .select(
                "recommended_actions, recommended_labels, rationale, confidence, context_alert_ids, created_at"
            )
            .eq("case_id", alert_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        existing_rows = _ensure_dict_rows(existing_response.data)
        if existing_rows:
            existing = existing_rows[0]
            existing_actions = [
                _normalize_action_choice_key(str(item))
                for item in (existing.get("recommended_actions") or [])
                if _normalize_action_choice_key(str(item))
                in ALLOWED_RECOMMENDATION_ACTIONS
            ]
            existing_labels = [
                str(item)
                for item in (existing.get("recommended_labels") or [])
                if str(item)
            ]
            if len(existing_labels) != len(existing_actions):
                default_label_map = {
                    "senior_activity_centre_staff": "Senior Activity Centre Staff",
                    "careline_staff": "CareLine Staff",
                    "community_responder": "Community Responder",
                    "police": "Police",
                    "scdf": "SCDF",
                    "call": "Call",
                }
                existing_labels = [
                    default_label_map.get(action, action.replace("_", " ").title())
                    for action in existing_actions
                ]
            context_alert_ids = [
                str(item)
                for item in (existing.get("context_alert_ids") or [])
                if str(item)
            ]
            return ActionRecommendationResponse(
                recommended_actions=existing_actions,
                recommended_labels=existing_labels,
                rationale=str(existing.get("rationale") or ""),
                confidence=_coerce_confidence(existing.get("confidence")),
                context_alert_ids=context_alert_ids,
                based_on_previous_alerts=len(context_alert_ids),
                fallback_used=False,
            )
    except Exception as exc:
        if not _is_missing_table_error(exc, "operator_action_recommendations"):
            raise

    current_response = (
        db.client.table("alerts")
        .select(
            "id, senior_id, risk_level, risk_score, status, ai_assessment, analysis_summary, "
            "transcription, translated_text, language_detected, keywords, created_at, "
            "seniors(id, full_name, preferred_language, medical_notes, address, sip_url)"
        )
        .eq("id", alert_id)
        .limit(1)
        .execute()
    )
    current_rows = _ensure_dict_rows(current_response.data)
    if not current_rows:
        raise HTTPException(status_code=404, detail="Alert not found")

    current_alert = current_rows[0]
    senior_id = current_alert.get("senior_id")
    if not isinstance(senior_id, str) or not senior_id:
        raise HTTPException(status_code=400, detail="Alert missing senior_id")

    choice_rows = [choice.model_dump() for choice in payload.available_choices]
    enabled_choices = [
        choice
        for choice in choice_rows
        if choice.get("enabled") is True
        and _normalize_action_choice_key(str(choice.get("action_key") or ""))
        in ALLOWED_RECOMMENDATION_ACTIONS
    ]
    if not enabled_choices:
        raise HTTPException(status_code=400, detail="No enabled choices provided")

    history_response = (
        db.client.table("alerts")
        .select(
            "id, created_at, risk_level, risk_score, status, ai_assessment, "
            "analysis_summary, transcription, translated_text, keywords"
        )
        .eq("senior_id", senior_id)
        .neq("id", alert_id)
        .order("created_at", desc=True)
        .limit(8)
        .execute()
    )
    history_rows = _ensure_dict_rows(history_response.data)
    history_ids = [str(row.get("id")) for row in history_rows if row.get("id")]

    action_rows: list[dict[str, Any]] = []
    if history_ids:
        try:
            actions_response = (
                db.client.table("operator_actions")
                .select("case_id, actions_taken, action_time")
                .in_("case_id", history_ids)
                .order("action_time", desc=True)
                .limit(100)
                .execute()
            )
            action_rows = _ensure_dict_rows(actions_response.data)
        except Exception as exc:
            if not _is_missing_table_error(exc, "operator_actions"):
                raise

    actions_by_case: dict[str, list[str]] = {}
    for row in action_rows:
        case_id = str(row.get("case_id") or "")
        if not case_id:
            continue
        action_name = _normalize_action_name(row.get("actions_taken"))
        if not action_name:
            continue
        actions_by_case.setdefault(case_id, []).append(action_name)

    compact_history: list[dict[str, Any]] = []
    for row in history_rows:
        case_id = str(row.get("id") or "")
        compact_history.append(
            {
                "id": case_id,
                "created_at": row.get("created_at"),
                "risk_level": row.get("risk_level"),
                "risk_score": row.get("risk_score"),
                "status": row.get("status"),
                "transcription": row.get("transcription"),
                "translated_text": row.get("translated_text"),
                "ai_assessment": row.get("ai_assessment") or row.get("analysis_summary"),
                "keywords": row.get("keywords"),
                "operator_actions": actions_by_case.get(case_id, [])[:5],
            }
        )

    provider = get_settings().ai_chat_model
    fallback = _fallback_action_recommendation(current_alert, enabled_choices)
    final_payload = dict(fallback)
    raw_response: dict[str, Any] = {}

    choice_labels = _choice_labels_by_key(choice_rows)
    enabled_keys = {
        _normalize_action_choice_key(str(choice.get("action_key") or ""))
        for choice in enabled_choices
    }

    try:
        ai_client = OpenAICompatibleClient()
        user_payload = {
            "current_alert": {
                "id": current_alert.get("id"),
                "risk_level": current_alert.get("risk_level"),
                "risk_score": current_alert.get("risk_score"),
                "status": current_alert.get("status"),
                "transcription": current_alert.get("transcription"),
                "translated_text": current_alert.get("translated_text"),
                "language_detected": current_alert.get("language_detected"),
                "keywords": current_alert.get("keywords"),
                "ai_assessment": current_alert.get("ai_assessment")
                or current_alert.get("analysis_summary"),
                "senior": current_alert.get("seniors"),
            },
            "available_choices": enabled_choices,
            "historical_alerts": compact_history,
        }
        ai_response = await ai_client._chatCompletion(
            system_message=ACTION_RECOMMENDATION_SYSTEM_PROMPT,
            user_message=json.dumps(user_payload),
            response_format="json_object",
        )
        parsed = json.loads(ai_response)
        parsed_dict = parsed if isinstance(parsed, dict) else {}
        raw_response = parsed_dict

        recommended_actions_raw = parsed_dict.get("recommended_actions")
        recommended_actions: list[str] = []
        if isinstance(recommended_actions_raw, list):
            for item in recommended_actions_raw:
                key = _normalize_action_choice_key(str(item or ""))
                if key and key in enabled_keys and key not in recommended_actions:
                    recommended_actions.append(key)

        if recommended_actions:
            final_payload = {
                "recommended_actions": recommended_actions,
                "rationale": str(parsed_dict.get("rationale") or "").strip()
                or fallback["rationale"],
                "confidence": _coerce_confidence(
                    parsed_dict.get("confidence"),
                    default=fallback["confidence"],
                ),
                "context_alert_ids": [
                    str(ref)
                    for ref in parsed_dict.get("context_alert_ids", [])
                    if str(ref) in set(history_ids)
                ],
                "fallback_used": False,
            }
    except Exception as exc:
        logger.warning("AI action recommendation failed: %s", exc)

    recommended_labels: list[str] = []
    for action_key_any in final_payload["recommended_actions"]:
        action_key = str(action_key_any)
        label = choice_labels.get(action_key)
        if isinstance(label, str) and label.strip():
            recommended_labels.append(label)
        else:
            recommended_labels.append(action_key.replace("_", " ").title())

    log_details = {
        "available_choices": choice_rows,
        "recommended_actions": final_payload["recommended_actions"],
        "recommended_labels": recommended_labels,
        "rationale": final_payload["rationale"],
        "confidence": final_payload["confidence"],
        "context_alert_ids": final_payload["context_alert_ids"],
        "historical_alert_count": len(compact_history),
        "fallback_used": final_payload["fallback_used"],
        "raw_response": raw_response,
    }
    _log_action_recommendation(
        alert_id=alert_id,
        details=log_details,
        provider=provider,
        action_status="fallback" if final_payload["fallback_used"] else "success",
    )

    return ActionRecommendationResponse(
        recommended_actions=final_payload["recommended_actions"],
        recommended_labels=recommended_labels,
        rationale=str(final_payload["rationale"]),
        confidence=_coerce_confidence(final_payload["confidence"]),
        context_alert_ids=list(final_payload["context_alert_ids"]),
        based_on_previous_alerts=len(compact_history),
        fallback_used=bool(final_payload["fallback_used"]),
    )


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
                .select(
                    "id, full_name, phone_number, address, preferred_language, created_at"
                )
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
            .select(
                "id, senior_id, created_at, status, risk_level, requires_operator, is_resolved"
            )
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        alerts_rows = _ensure_dict_rows(alerts_response.data)
    except Exception as exc:
        if _is_missing_column_error(exc, "alerts.is_resolved"):
            alerts_response = (
                db.client.table("alerts")
                .select(
                    "id, senior_id, created_at, status, risk_level, requires_operator"
                )
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
        raise HTTPException(
            status_code=400, detail="Failed to create emergency contact"
        )
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
