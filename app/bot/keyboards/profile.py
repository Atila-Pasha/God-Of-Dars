from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LevelConfirmationCallback, ProfileCallback


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 اطلاعات کاربری",
                    callback_data=ProfileCallback(action="info").pack(),
                ),
                InlineKeyboardButton(
                    text="⬆️ ارتقای سطح",
                    callback_data=ProfileCallback(action="upgrade").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 بازگشت به منوی اصلی",
                    callback_data=ProfileCallback(action="back").pack(),
                )
            ],
        ]
    )


def level_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ تأیید ارتقا",
            callback_data=LevelConfirmationCallback(decision="confirm").pack(),
        ),
        InlineKeyboardButton(
            text="❌ لغو",
            callback_data=LevelConfirmationCallback(decision="cancel").pack(),
        ),
    ]])
