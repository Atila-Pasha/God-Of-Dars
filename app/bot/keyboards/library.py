from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LibraryCallback


def library_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 سؤال روزانه",
                    callback_data=LibraryCallback(action="daily").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 سؤال گروه",
                    callback_data=LibraryCallback(action="group").pack(),
                )
            ],
        ]
    )


def answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ پاسخ دادن",
                    callback_data=LibraryCallback(action="daily").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=LibraryCallback(action="cancel").pack(),
                ),
            ]
        ]
    )


def group_answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ پاسخ دادن",
                    callback_data=LibraryCallback(action="group").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=LibraryCallback(action="cancel").pack(),
                ),
            ]
        ]
    )
