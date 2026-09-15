from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LeaderboardCallback
from app.services.leaderboard_service import LeaderboardKind, LeaderboardPeriod


def leaderboard_keyboard(
    *,
    active_kind: LeaderboardKind | None = None,
    active_period: LeaderboardPeriod = "weekly",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✓ " if active_kind == "commander" else "") + "👑 فرمانده",
                callback_data=LeaderboardCallback(
                    action="commander", period=active_period
                ).pack(),
            ),
            InlineKeyboardButton(
                text=("✓ " if active_kind == "student" else "") + "📚 دانش‌آموز",
                callback_data=LeaderboardCallback(
                    action="student", period=active_period
                ).pack(),
            ),
            InlineKeyboardButton(
                text=("✓ " if active_kind == "fighter" else "") + "⚔️ مبارز",
                callback_data=LeaderboardCallback(
                    action="fighter", period=active_period
                ).pack(),
            ),
        ],
    ]
    if active_kind is not None:
        periods: tuple[tuple[LeaderboardPeriod, str], ...] = (
            ("daily", "روزانه"),
            ("weekly", "هفتگی"),
            ("monthly", "ماهانه"),
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✓ " if period == active_period else "") + label,
                    callback_data=LeaderboardCallback(
                        action=active_kind, period=period
                    ).pack(),
                )
                for period, label in periods
            ],
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ بازگشت به پروفایل",
                callback_data=LeaderboardCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
