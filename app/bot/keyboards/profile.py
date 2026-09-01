from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import ProfileCallback


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 بروزرسانی آمار",
                    callback_data=ProfileCallback(action="refresh").pack(),
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
