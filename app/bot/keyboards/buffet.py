from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.callbacks import (
    BuffetCallback,
    BuffetMenuCallback,
    ShieldCallback,
    ShieldPurchaseCallback,
)
from app.bot.custom_emojis import premium_emoji_id
from app.core.game_logic import BuffetConversion
from app.models.shield import Shield
from app.models.user_shield import UserShield

RESOURCE_LABELS = {"COIN": "طلا", "DIAMOND": "الماس"}
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
        rows.append(
            [
                InlineKeyboardButton(
                    text=f">> {RESOURCE_LABELS[option.target.value]} ",
                    icon_custom_emoji_id=RESOURCE_CUSTOM_EMOJI_IDS[option.source.value],
                    callback_data=callback_data,
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بوفه", callback_data=BuffetMenuCallback(action="back").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buffet_menu_keyboard() -> ReplyKeyboardMarkup:
    """Replace the main user keyboard while the user is inside the buffet."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 تبدیل منابع")],
            [KeyboardButton(text="🛡 خرید سپر")],
            [KeyboardButton(text="👨‍🏫 خرید دبیر")],
            [KeyboardButton(text="بازگشت به منو اصلی")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


def buffet_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=BuffetMenuCallback(action="back").pack(),
                )
            ],
        ]
    )


def shield_catalog_keyboard(
    shields: list[Shield], owned: list[UserShield] | None = None
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{shield.name} — {shield.duration_minutes} دقیقه",
                icon_custom_emoji_id=premium_emoji_id("🛡"),
                callback_data=ShieldCallback(action="buy", shield_id=shield.id).pack(),
            )
        ]
        for shield in shields
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بوفه",
                callback_data=ShieldCallback(action="back", shield_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shield_purchase_confirmation(shield: Shield) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید خرید",
                    callback_data=ShieldPurchaseCallback(
                        decision="confirm", shield_id=shield.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=ShieldPurchaseCallback(
                        decision="cancel", shield_id=shield.id
                    ).pack(),
                ),
            ]
        ]
    )


def shield_inventory_keyboard(shields: list[UserShield]) -> InlineKeyboardMarkup:
    rows = []
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بوفه",
                callback_data=ShieldCallback(action="back", shield_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
