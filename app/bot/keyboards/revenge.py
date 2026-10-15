from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import RevengeCallback


def revenge_keyboard(attack_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="نه",
                    style="success",
                    callback_data=RevengeCallback(
                        action="no", attack_id=attack_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="انتقام",
                    icon_custom_emoji_id="5823192436024813346",
                    style="danger",
                    callback_data=RevengeCallback(
                        action="attack", attack_id=attack_id
                    ).pack(),
                ),
            ]
        ]
    )
