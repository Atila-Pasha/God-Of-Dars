from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import HelpCallback

HELP_SECTIONS = (
    ("⚔️ راهنمای حمله", "attack"),
    ("🏫 راهنمای مدرسه", "school"),
    ("🍽 راهنمای بوفه", "buffet"),
    ("📚 راهنمای کتابخانه", "library"),
    ("🧙 راهنمای پروفایل", "profile"),
    ("⛏ راهنمای معدن", "mine"),
    ("👥 راهنمای دعوت", "referral"),
)


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=HelpCallback(section=section).pack(),
                )
                for label, section in HELP_SECTIONS[index : index + 2]
            ]
            for index in range(0, len(HELP_SECTIONS), 2)
        ]
    )
