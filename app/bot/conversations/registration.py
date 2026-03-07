from __future__ import annotations

import calendar
import re
from datetime import datetime

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.i18n import DEFAULT_COUNTRY_CODE, t
from app.bot.keyboards.inline import language_keyboard, skip_medical_notes_keyboard
from app.services.database import DatabaseService

REGISTRATION = "registration"

(
    SELECT_LANGUAGE,
    ASK_FULL_NAME,
    ASK_PHONE_NUMBER,
    ASK_ADDRESS,
    ASK_BIRTH_YEAR,
    ASK_BIRTH_MONTH,
    ASK_BIRTH_DAY,
    ASK_MEDICAL_NOTES,
) = range(8)

MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 100
MIN_ADDRESS_LENGTH = 10
MAX_ADDRESS_LENGTH = 500
MAX_MEDICAL_NOTES_LENGTH = 2000
PHONE_DIGITS = 8
MIN_AGE = 18


def _registration_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if REGISTRATION not in context.user_data:
        context.user_data[REGISTRATION] = {}
    return context.user_data[REGISTRATION]


def _is_valid_day(year: int, month: int, day: int) -> bool:
    try:
        _, max_day = calendar.monthrange(year, month)
        return 1 <= day <= max_day
    except ValueError:
        return False


async def _prompt_next(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")

    if state == ASK_FULL_NAME:
        await update.effective_chat.send_message(t(lang, "ask_full_name"))
    elif state == ASK_PHONE_NUMBER:
        await update.effective_chat.send_message(t(lang, "ask_phone_number"))
    elif state == ASK_ADDRESS:
        await update.effective_chat.send_message(t(lang, "ask_address"))
    elif state == ASK_BIRTH_YEAR:
        await update.effective_chat.send_message(t(lang, "ask_birth_year"))
    elif state == ASK_BIRTH_MONTH:
        await update.effective_chat.send_message(t(lang, "ask_birth_month"))
    elif state == ASK_BIRTH_DAY:
        await update.effective_chat.send_message(t(lang, "ask_birth_day"))
    elif state == ASK_MEDICAL_NOTES:
        await update.effective_chat.send_message(
            t(lang, "ask_medical_notes"),
            reply_markup=skip_medical_notes_keyboard(t(lang, "skip")),
        )
    return state


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.application.bot_data["db_service"]
    telegram_user_id = str(update.effective_user.id)
    senior = db.get_senior_by_telegram_user_id(telegram_user_id)

    if senior:
        await update.message.reply_text(t(senior.preferred_language, "welcome_back"))
        return ConversationHandler.END

    context.user_data[REGISTRATION] = {}
    await update.message.reply_text(t("en", "welcome_new"))
    await update.message.reply_text(t("en", "pick_language"), reply_markup=language_keyboard())
    return SELECT_LANGUAGE


async def handle_language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    language = query.data.split(":", maxsplit=1)[1]
    data = _registration_data(context)
    data["preferred_language"] = language

    await query.edit_message_text(t(language, "pick_language"))
    return await _prompt_next(update, context, ASK_FULL_NAME)


async def handle_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    text = update.message.text.strip()

    if len(text) < MIN_NAME_LENGTH or len(text) > MAX_NAME_LENGTH:
        await update.message.reply_text(t(lang, "invalid_name"))
        return ASK_FULL_NAME

    data["full_name"] = text
    return await _prompt_next(update, context, ASK_PHONE_NUMBER)


async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    text = update.message.text.strip()

    cleaned = re.sub(r"[\s\-]", "", text)

    if not cleaned.isdigit() or len(cleaned) != PHONE_DIGITS:
        await update.message.reply_text(t(lang, "invalid_phone"))
        return ASK_PHONE_NUMBER

    normalized_phone = f"{DEFAULT_COUNTRY_CODE}{cleaned}"
    data["phone_number"] = normalized_phone
    return await _prompt_next(update, context, ASK_ADDRESS)


async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    text = update.message.text.strip()

    if len(text) < MIN_ADDRESS_LENGTH or len(text) > MAX_ADDRESS_LENGTH:
        await update.message.reply_text(t(lang, "invalid_address"))
        return ASK_ADDRESS

    data["address"] = text
    return await _prompt_next(update, context, ASK_BIRTH_YEAR)


async def handle_birth_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(t(lang, "invalid_number"))
        return ASK_BIRTH_YEAR

    year = int(text)
    current_year = datetime.utcnow().year
    age = current_year - year

    if year < 1900 or age < MIN_AGE:
        await update.message.reply_text(t(lang, "invalid_birth_year"))
        return ASK_BIRTH_YEAR

    data["birth_year"] = year
    data["_temp_age"] = age
    return await _prompt_next(update, context, ASK_BIRTH_MONTH)


async def handle_birth_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(t(lang, "invalid_number"))
        return ASK_BIRTH_MONTH

    month = int(text)
    if month < 1 or month > 12:
        await update.message.reply_text(t(lang, "invalid_birth_month"))
        return ASK_BIRTH_MONTH

    data["birth_month"] = month
    return await _prompt_next(update, context, ASK_BIRTH_DAY)


async def handle_birth_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(t(lang, "invalid_number"))
        return ASK_BIRTH_DAY

    day = int(text)
    year = data.get("birth_year", 2000)
    month = data.get("birth_month", 1)

    if not _is_valid_day(year, month, day):
        await update.message.reply_text(t(lang, "invalid_birth_day"))
        return ASK_BIRTH_DAY

    data["birth_day"] = day
    return await _prompt_next(update, context, ASK_MEDICAL_NOTES)


async def handle_medical_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = _registration_data(context)
    lang = data.get("preferred_language", "en")
    notes = update.message.text.strip()

    if len(notes) > MAX_MEDICAL_NOTES_LENGTH:
        await update.message.reply_text(t(lang, "invalid_medical_notes"))
        return ASK_MEDICAL_NOTES

    data["medical_notes"] = notes if notes else None
    return await _finalize_registration(update, context)


async def skip_medical_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = _registration_data(context)
    data["medical_notes"] = None
    return await _finalize_registration(update, context)


async def _finalize_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: DatabaseService = context.application.bot_data["db_service"]
    data = _registration_data(context)
    telegram_user_id = str(update.effective_user.id)
    payload = {
        "full_name": data["full_name"],
        "phone_number": data["phone_number"],
        "telegram_user_id": telegram_user_id,
        "address": data["address"],
        "birth_year": data["birth_year"],
        "birth_month": data["birth_month"],
        "birth_day": data["birth_day"],
        "preferred_language": data["preferred_language"],
        "medical_notes": data["medical_notes"],
    }
    db.create_senior(payload)
    await update.effective_chat.send_message(t(data.get("preferred_language"), "registration_complete"))
    context.user_data.pop(REGISTRATION, None)
    return ConversationHandler.END


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(REGISTRATION, None)
    await update.message.reply_text("Registration cancelled. Send /start when ready.")
    return ConversationHandler.END


def build_registration_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_registration)],
        states={
            SELECT_LANGUAGE: [CallbackQueryHandler(handle_language_selected, pattern=r"^lang:")],
            ASK_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name)],
            ASK_PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address)],
            ASK_BIRTH_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birth_year)],
            ASK_BIRTH_MONTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birth_month)],
            ASK_BIRTH_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birth_day)],
            ASK_MEDICAL_NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_medical_notes),
                CallbackQueryHandler(skip_medical_notes, pattern=r"^skip:medical_notes$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True,
        name="registration_conversation",
        persistent=False,
    )
