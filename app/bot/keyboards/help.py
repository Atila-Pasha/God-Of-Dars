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

HELP_SECTIONS: tuple[tuple[str, HelpSection], ...] = (
    ("🧭 راهنمای کامل بازی", "overview"),
    ("⚔️ راهنمای حمله", "attack"),
    ("🏫 راهنمای مدرسه", "school"),
    ("🍽 راهنمای بوفه", "buffet"),
    ("📚 راهنمای کتابخانه", "library"),
    ("🧙 راهنمای پروفایل", "profile"),
    ("⛏ راهنمای معدن", "mine"),
    ("👥 راهنمای دعوت", "referral"),
    ("شعارهای قابل استفاده", "slogans"),
)


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    icon_custom_emoji_id=(
                        "5825961702088254236" if section == "slogans" else None
                    ),
                    callback_data=HelpCallback(section=section).pack(),
                )
                for label, section in HELP_SECTIONS[index : index + 2]
            ]
            for index in range(0, len(HELP_SECTIONS), 2)
        ]
    )
