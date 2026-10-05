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

RESOURCE_EMOJIS = {"COIN": "🪙", "DIAMOND": "💎"}


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
                    text=(
                        "تبدیل الماس به طلا"
                        if option.source.value == "DIAMOND"
                        else "تبدیل طلا به الماس"
                    ),
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
            [
                KeyboardButton(
                    text="تبدیل منابع", icon_custom_emoji_id="5220021677244559322"
                )
            ],
            [
                KeyboardButton(
                    text="فهرست سپر ها", icon_custom_emoji_id="5825861861278490879"
                )
            ],
            [
                KeyboardButton(
                    text="خرید دبیر", icon_custom_emoji_id="5784897390922174736"
                )
            ],
            [
                KeyboardButton(
                    text="بازگشت به منو اصلی",
                    icon_custom_emoji_id="5235864325540815679",
                )
            ],
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
    shields: list[Shield],
    owned: list[UserShield] | None = None,
    *,
    player_level: int = 1,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{shield.name} — سطح {shield.unlock_level}"
                if shield.unlock_level > player_level
                else shield.name,
                icon_custom_emoji_id=SHIELD_ICONS.get(
                    shield.name, premium_emoji_id("🛡")
                ),
                callback_data=ShieldCallback(action="buy", shield_id=shield.id).pack(),
            )
        ]
        for shield in shields
        if shield.unlock_level <= player_level
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


SHIELD_ICONS = {
    "سپر زنگ تفریح": "5825861861278490879",
    "سپر آلودگی هوا": "5917839500750364054",
    "سپر محمدی": "5915796556606348792",
    "سپر کاظمی": "5917954648823570305",
    "سپر خسروپناه": "5915702157520150395",
}


def shield_purchase_confirmation(shield: Shield) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید خرید",
                    style="success",
                    callback_data=ShieldPurchaseCallback(
                        decision="confirm", shield_id=shield.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    style="danger",
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
