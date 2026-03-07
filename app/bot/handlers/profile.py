from __future__ import annotations

import re

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
from app.bot.keyboards.inline import profile_update_keyboard
from app.services.database import DatabaseService

PROFILE = "profile"

(
    VIEW_PROFILE,
    SELECT_UPDATE_FIELD,
    INPUT_NEW_VALUE,
) = range(3)

MIN_ADDRESS_LENGTH = 10
MAX_ADDRESS_LENGTH = 500
MAX_MEDICAL_NOTES_LENGTH = 2000
PHONE_DIGITS = 8


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: DatabaseService = context.application.bot_data["db_service"]
    telegram_user_id = str(update.effective_user.id)
    senior = db.get_senior_by_telegram_user_id(telegram_user_id)

    if not senior:
        await update.message.reply_text(t("en", "not_registered"))
        return ConversationHandler.END

    lang = senior.preferred_language or "en"

    birthday = f"{senior.birth_day}/{senior.birth_month}/{senior.birth_year}" if senior.birth_year else "-"
    medical_notes = senior.medical_notes or "-"

    profile_text = (
        f"*{t(lang, 'profile_title')}*\n\n"
        f"{t(lang, 'profile_name')}: {senior.full_name}\n"
        f"{t(lang, 'profile_phone')}: {senior.phone_number}\n"
        f"{t(lang, 'profile_address')}: {senior.address}\n"
        f"{t(lang, 'profile_birthday')}: {birthday}\n"
        f"{t(lang, 'profile_language')}: {senior.preferred_language}\n"
        f"{t(lang, 'profile_medical_notes')}: {medical_notes}\n"
    )

    await update.message.reply_text(
        profile_text,
        parse_mode="Markdown",
        reply_markup=profile_update_keyboard(lang),
    )
    return SELECT_UPDATE_FIELD


async def handle_update_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "update:cancel":
        await query.edit_message_text(t("en", "welcome_back"))
        return ConversationHandler.END

    field = data.split(":", 1)[1]
    context.user_data[PROFILE] = {"update_field": field}

    db: DatabaseService = context.application.bot_data["db_service"]
    telegram_user_id = str(update.effective_user.id)
    senior = db.get_senior_by_telegram_user_id(telegram_user_id)
    lang = senior.preferred_language or "en" if senior else "en"

    prompt_key = f"ask_{field}"
    await query.edit_message_text(t(lang, prompt_key))

    return INPUT_NEW_VALUE


async def handle_update_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: DatabaseService = context.application.bot_data["db_service"]
    telegram_user_id = str(update.effective_user.id)
    senior = db.get_senior_by_telegram_user_id(telegram_user_id)

    if not senior:
        await update.message.reply_text(t("en", "not_registered"))
        return ConversationHandler.END

    lang = senior.preferred_language or "en"
    profile_data = context.user_data.get(PROFILE, {})
    field = profile_data.get("update_field")

    if not field:
        return ConversationHandler.END

    new_value = update.message.text.strip()

    if field == "phone_number":
        cleaned = re.sub(r"[\s\-]", "", new_value)
        if not cleaned.isdigit() or len(cleaned) != PHONE_DIGITS:
            await update.message.reply_text(t(lang, "invalid_phone"))
            return INPUT_NEW_VALUE
        new_value = f"{DEFAULT_COUNTRY_CODE}{cleaned}"

    elif field == "address":
        if len(new_value) < MIN_ADDRESS_LENGTH or len(new_value) > MAX_ADDRESS_LENGTH:
            await update.message.reply_text(t(lang, "invalid_address"))
            return INPUT_NEW_VALUE

    elif field == "medical_notes":
        if len(new_value) > MAX_MEDICAL_NOTES_LENGTH:
            await update.message.reply_text(t(lang, "invalid_medical_notes"))
            return INPUT_NEW_VALUE
        new_value = new_value if new_value else None

    db.update_senior(senior.id, {field: new_value})

    field_label_key = f"profile_{field}"
    field_label = t(lang, field_label_key)
    success_message = t(lang, "profile_update_success").format(field=field_label)

    await update.message.reply_text(success_message)

    context.user_data.pop(PROFILE, None)
    return ConversationHandler.END


async def cancel_profile_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(PROFILE, None)
    await update.message.reply_text("Profile update cancelled.")
    return ConversationHandler.END


def build_profile_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("profile", show_profile)],
        states={
            SELECT_UPDATE_FIELD: [
                CallbackQueryHandler(handle_update_selection, pattern=r"^update:")
            ],
            INPUT_NEW_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_update_value)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_profile_update)],
        allow_reentry=True,
        name="profile_conversation",
        persistent=False,
    )
