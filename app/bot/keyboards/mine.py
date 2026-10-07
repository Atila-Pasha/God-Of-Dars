from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import MineCallback


def mine_keyboard(*, can_upgrade: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="برداشت طلا",
                icon_custom_emoji_id="5823329527085931340",
                callback_data=MineCallback(action="collect_coin").pack(),
            ),
            InlineKeyboardButton(
                text="برداشت الماس",
                icon_custom_emoji_id="5825753314570018832",
                callback_data=MineCallback(action="collect_diamond").pack(),
            ),
        ]
    ]
    if can_upgrade:
        rows.append(
            [
                InlineKeyboardButton(
                    text="ارتقای معدن",
                    icon_custom_emoji_id="5866060208253441223",
                    style="success",
                    callback_data=MineCallback(action="upgrade").pack(),
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
                    style="success",
                    callback_data=MineCallback(action="confirm_upgrade").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    style="danger",
                    callback_data=MineCallback(action="cancel_upgrade").pack(),
                ),
            ]
        ]
    )
