from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.callbacks import BuffetCallback, BuffetMenuCallback, ShieldCallback
from app.core.game_logic import BuffetConversion
from app.models.shield import Shield
from app.models.user_shield import UserShield

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
            [KeyboardButton(text="🔙 منوی اصلی")],
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
                text=f"🛡 {shield.name} — {shield.purchase_price} سکه",
                callback_data=ShieldCallback(action="buy", shield_id=shield.id).pack(),
            )
        ]
        for shield in shields
    ]
    for item in owned or []:
        status = "✅ فعال" if item.is_equipped else "⚪ فعال‌سازی"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {item.shield.name} ({item.quantity})",
                    callback_data=ShieldCallback(
                        action="equip", shield_id=item.id
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بوفه",
                callback_data=ShieldCallback(action="back", shield_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shield_inventory_keyboard(shields: list[UserShield]) -> InlineKeyboardMarkup:
    rows = []
    for owned in shields:
        status = "✅ فعال" if owned.is_equipped else "⚪ فعال‌سازی"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {owned.shield.name} ({owned.quantity})",
                    callback_data=ShieldCallback(
                        action="equip", shield_id=owned.id
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بوفه",
                callback_data=ShieldCallback(action="back", shield_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
