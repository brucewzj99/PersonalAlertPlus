from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.i18n import LANGUAGE_OPTIONS, t


def language_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(label, callback_data=f"lang:{code}") for label, code in LANGUAGE_OPTIONS]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


def skip_medical_notes_keyboard(skip_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(skip_label, callback_data="skip:medical_notes")]]
    )


def profile_update_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t(lang, "update_phone"), callback_data="update:phone_number")],
        [InlineKeyboardButton(t(lang, "update_address"), callback_data="update:address")],
        [InlineKeyboardButton(t(lang, "update_medical_notes"), callback_data="update:medical_notes")],
        [InlineKeyboardButton(t(lang, "profile_cancel"), callback_data="update:cancel")],
    ]
    return InlineKeyboardMarkup(buttons)
