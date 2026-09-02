from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import BuffetCallback
from app.core.game_logic import BuffetConversion

RESOURCE_LABELS = {"COIN": "طلا", "DIAMOND": "الماس", "BANANA": "موز"}
RESOURCE_CUSTOM_EMOJI_IDS = {
    "COIN": "5765076709556623066",
    "DIAMOND": "5462902520215002477",
    "BANANA": "5091424266138682339",
}


def buffet_keyboard(options: tuple[BuffetConversion, ...]) -> InlineKeyboardMarkup:
    rows = []
    for option in options:
        callback_data = BuffetCallback(
            action="convert",
            source=option.source.value,
            target=option.target.value,
        ).pack()
        rows.append([
            InlineKeyboardButton(
                text=f">> {RESOURCE_LABELS[option.target.value]} ",
                icon_custom_emoji_id=RESOURCE_CUSTOM_EMOJI_IDS[option.source.value],
                callback_data=callback_data,
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
