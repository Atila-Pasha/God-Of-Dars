from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import GlobalRankCallback, LeaderboardCallback
from app.services.leaderboard_service import LeaderboardKind, LeaderboardPeriod


def leaderboard_keyboard(
    *,
    active_kind: LeaderboardKind | None = None,
    active_period: LeaderboardPeriod = "weekly",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✓ " if active_kind == "commander" else "") + "فرمانده",
                icon_custom_emoji_id="5825647731388981287",
                callback_data=LeaderboardCallback(
                    action="commander", period=active_period
                ).pack(),
            ),
            InlineKeyboardButton(
                text=("✓ " if active_kind == "student" else "") + "دانش‌آموز",
                icon_custom_emoji_id="5918211539407478280",
                callback_data=LeaderboardCallback(
                    action="student", period=active_period
                ).pack(),
            ),
            InlineKeyboardButton(
                text=("✓ " if active_kind == "fighter" else "") + "سراسری",
                icon_custom_emoji_id="5823430604846276719",
                callback_data=LeaderboardCallback(
                    action="fighter", period=active_period
                ).pack(),
            ),
        ],
    ]
    if active_kind is not None and active_kind != "fighter":
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


def global_rank_keyboard(
    page: int, pages: int, *, private: bool = False
) -> InlineKeyboardMarkup:
    navigation = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                text="صفحه قبل",
                icon_custom_emoji_id="5235864325540815679",
                callback_data=GlobalRankCallback(page=page - 1).pack(),
            )
        )
    if page < pages:
        navigation.append(
            InlineKeyboardButton(
                text="صفحه بعد",
                icon_custom_emoji_id="5823430604846276719",
                callback_data=GlobalRankCallback(page=page + 1).pack(),
            )
        )
    rows = [navigation] if navigation else []
    rows.append(
        [
            InlineKeyboardButton(
                text="تازه‌سازی جدول",
                icon_custom_emoji_id="6039539366177541657",
                callback_data=GlobalRankCallback(page=page).pack(),
            )
        ]
    )
    if private:
        rows.append(
            [
                InlineKeyboardButton(
                    text="بازگشت به برترین‌ها",
                    icon_custom_emoji_id="5235864325540815679",
                    callback_data=LeaderboardCallback(action="menu").pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
