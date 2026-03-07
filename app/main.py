from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.application import build_bot_application
from app.brain.router import router as brain_router, set_telegram_bot
from app.api.v1.operator import router as operator_router
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
telegram_app = build_bot_application()
scheduler = AsyncIOScheduler()


async def run_conversation_timeout_check():
    """Run timeout check for active conversations."""
    try:
        from app.brain.services.conversation_timeout import (
            ConversationTimeoutHandler,
            DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
        )
        handler = ConversationTimeoutHandler()
        results = handler.check_and_timeout_conversations(
            timeout_seconds=DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS
        )
        if results:
            logger.info(f"Timeout check: {len(results)} conversations timed out")
    except Exception as e:
        logger.error(f"Error in timeout check: {e}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()
    set_telegram_bot(telegram_app.bot)

    scheduler.add_job(
        run_conversation_timeout_check,
        "interval",
        seconds=5,
        id="conversation_timeout_check",
    )
    scheduler.start()
    logger.info("Started conversation timeout scheduler (every 5 seconds)")

    if settings.bot_mode == "webhook":
        if not settings.bot_webhook_url:
            raise RuntimeError("BOT_WEBHOOK_URL is required when BOT_MODE=webhook")
        await telegram_app.bot.set_webhook(
            url=settings.bot_webhook_url,
            secret_token=settings.bot_webhook_secret,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        await telegram_app.bot.delete_webhook(drop_pending_updates=False)
        if telegram_app.updater is None:
            raise RuntimeError("Polling mode requires an updater-enabled application")
        await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    yield
    scheduler.shutdown()
    if settings.bot_mode == "webhook":
        await telegram_app.bot.delete_webhook()
    else:
        if telegram_app.updater is None:
            raise RuntimeError("Polling mode requires an updater-enabled application")
        await telegram_app.updater.stop()
    await telegram_app.stop()
    await telegram_app.shutdown()


app = FastAPI(title="PersonalAlertPlus Bot API", lifespan=lifespan)

app.include_router(brain_router)
app.include_router(operator_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.bot_mode != "webhook":
        raise HTTPException(
            status_code=404, detail="Webhook route disabled in polling mode"
        )

    if (
        settings.bot_webhook_secret
        and x_telegram_bot_api_secret_token != settings.bot_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
