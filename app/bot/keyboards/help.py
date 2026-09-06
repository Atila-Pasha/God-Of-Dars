from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import HelpCallback

HELP_SECTIONS = (
    ("⚔️ حمله", "attack"),
    ("🏫 مدرسه و دبیرها", "school"),
    ("🍽 بوفه و خرید", "buffet"),
    ("📚 کتابخانه", "library"),
    ("🧙 پروفایل", "profile"),
    ("⛏ معدن منابع", "mine"),
    ("👥 دعوت دوستان", "referral"),
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
