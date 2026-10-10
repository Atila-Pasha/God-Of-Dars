from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import HelpCallback

HelpSection = Literal[
    "overview",
    "attack",
    "school",
    "buffet",
    "library",
    "profile",
    "mine",
    "referral",
    "slogans",
]

HELP_SECTIONS: tuple[tuple[str, HelpSection, str], ...] = (
    ("راهنمای کامل بازی", "overview", "6039539366177541657"),
    ("راهنمای حمله", "attack", "5823192436024813346"),
    ("راهنمای مدرسه", "school", "5825697157872623308"),
    ("راهنمای بوفه", "buffet", "5823511728188563725"),
    ("راهنمای کتابخانه", "library", "5825629907274703191"),
    ("راهنمای پروفایل", "profile", "5825647731388981287"),
    ("راهنمای معدن", "mine", "5823474022670671455"),
    ("راهنمای دعوت", "referral", "5823282613158158030"),
    ("شعارهای قابل استفاده", "slogans", "5825961702088254236"),
)


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    icon_custom_emoji_id=emoji_id,
                    callback_data=HelpCallback(section=section).pack(),
                )
                for label, section, emoji_id in HELP_SECTIONS[index : index + 2]
            ]
            for index in range(0, len(HELP_SECTIONS), 2)
        ]
    )
