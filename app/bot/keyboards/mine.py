from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import MineCallback


def mine_keyboard(*, can_upgrade: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_upgrade:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬆️ ارتقای معدن",
                    callback_data=MineCallback(action="upgrade").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 منوی اصلی", callback_data=MineCallback(action="back").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mine_upgrade_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید ارتقا",
                    callback_data=MineCallback(action="confirm_upgrade").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=MineCallback(action="cancel_upgrade").pack(),
                ),
            ]
        ]
    )
