from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import ChannelCallback, FirstLoginCallback
from app.services.subscription_service import SubscriptionService


def join_channel_keyboard(
    subscription_service: SubscriptionService,
) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"عضویت در {channel}",
                icon_custom_emoji_id="5825791209066471425",
                url=subscription_service.channel_url(channel),
            )
        ]
        for channel in subscription_service.channels
    ]
    if subscription_service.channels:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="بررسی عضویت",
                    icon_custom_emoji_id="5825709849500985213",
                    callback_data=ChannelCallback(action="check").pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def first_login_guide_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="فهمیدم؛ بزن بریم!",
                    icon_custom_emoji_id="5825709849500985213",
                    callback_data=FirstLoginCallback(action="confirm").pack(),
                )
            ]
        ]
    )
