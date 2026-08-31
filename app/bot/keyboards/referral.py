from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def referral_keyboard(invite_link: str | None) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if invite_link:
        share_url = (
            "https://t.me/share/url?url="
            f"{quote(invite_link, safe='')}"
            f"&text={quote('به بازی ما بپیوند!', safe='')}"
        )
        buttons.append(
            [InlineKeyboardButton(text="📤 اشتراک‌گذاری لینک دعوت", url=share_url)]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
