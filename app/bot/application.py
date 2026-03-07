from telegram.ext import Application, MessageHandler, filters

from app.bot.conversations.registration import build_registration_conversation
from app.bot.handlers.alerts import handle_text_alert, handle_voice_alert
from app.bot.handlers.profile import build_profile_conversation
from app.bot.handlers.escalate import build_escalate_handler
from app.config import get_settings
from app.services.api_client import BackendApiClient
from app.services.database import DatabaseService
from app.services.storage import StorageService


def build_bot_application() -> Application:
    settings = get_settings()
    application = Application.builder().token(settings.telegram_bot_token).build()

    db_service = DatabaseService()
    application.bot_data["db_service"] = db_service
    application.bot_data["storage_service"] = StorageService(db_service)
    application.bot_data["api_client"] = BackendApiClient()

    application.add_handler(build_registration_conversation())
    application.add_handler(build_profile_conversation())
    application.add_handler(build_escalate_handler())
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_alert))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_alert)
    )

    return application
