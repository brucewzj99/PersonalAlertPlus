from datetime import datetime, timezone
from telegram import Bot

from fastapi import APIRouter, HTTPException

from app.brain.schemas import BrainAlertPayload, BrainAlertResponse, BrainHealthResponse
from app.brain.orchestrator import BrainOrchestrator
from app.services.database import DatabaseService
from app.config import get_settings

router = APIRouter(prefix="/api/v1/brain", tags=["brain"])

_orchestrator_instance: BrainOrchestrator | None = None
_telegram_bot: Bot | None = None


def set_telegram_bot(bot: Bot) -> None:
    """Called during app startup to set the Telegram bot instance."""
    print("Setting Telegram bot instance in brain router")
    global _telegram_bot
    _telegram_bot = bot


def get_orchestrator() -> BrainOrchestrator:
    print("Getting BrainOrchestrator instance")
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = BrainOrchestrator(telegram_bot=_telegram_bot)
    return _orchestrator_instance


@router.post("/alerts/ingest", response_model=BrainAlertResponse)
async def ingest_alert(payload: BrainAlertPayload) -> BrainAlertResponse:
    """Ingest and process a new alert from the Telegram bot."""
    print(f"Received alert payload: {payload}")
    if not payload.audio_url and not payload.audio_base64 and not payload.text:
        raise HTTPException(
            status_code=400,
            detail="Either audio_url, audio_base64, or text must be provided",
        )

    orchestrator = get_orchestrator()
    result = await orchestrator.process_alert(payload)
    return result


@router.get("/health", response_model=BrainHealthResponse)
async def brain_health_check() -> BrainHealthResponse:
    """Health check for brain services."""
    settings = get_settings()
    db_status = "unknown"
    ai_status = "unknown"

    try:
        db = DatabaseService()
        db.client.table("seniors").select("id").limit(1).execute()
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        ai_status = f"ok ({settings.ai_chat_model})"
    except Exception:
        ai_status = "error"

    return BrainHealthResponse(
        status="ok" if db_status == "ok" and ai_status == "ok" else "degraded",
        ai_provider=ai_status,
        database=db_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
