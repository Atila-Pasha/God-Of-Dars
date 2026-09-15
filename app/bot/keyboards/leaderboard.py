from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LeaderboardCallback


def leaderboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👑 برترین فرمانده‌ها",
                    callback_data=LeaderboardCallback(action="commander").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 برترین دانش‌آموزها",
                    callback_data=LeaderboardCallback(action="student").pack(),
                ),
                InlineKeyboardButton(
                    text="⚔️ برترین مبارزها",
                    callback_data=LeaderboardCallback(action="fighter").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ بازگشت به پروفایل",
                    callback_data=LeaderboardCallback(action="back").pack(),
                )
            ],
        ]
    )
