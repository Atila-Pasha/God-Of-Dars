"""One shield icon source for messages and buttons."""

from __future__ import annotations

from app.bot.banners import emoji, escape
from app.bot.custom_emojis import premium_emoji_id
from app.models.shield import Shield

DEFAULT_SHIELD_EMOJI_ID = "5825861861278490879"
DEFAULT_SHIELD_FALLBACK = "🛡️"


def _value(shield: Shield) -> str | None:
    value = getattr(shield, "emoji", None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def shield_emoji_id(shield: Shield) -> str | None:
    value = _value(shield)
    if value is None:
        return DEFAULT_SHIELD_EMOJI_ID
    return premium_emoji_id(value)


def shield_plain_icon(shield: Shield) -> str:
    value = _value(shield)
    return value if value and not value.isdigit() else DEFAULT_SHIELD_FALLBACK


def shield_icon(shield: Shield) -> str:
    emoji_id = shield_emoji_id(shield)
    fallback = shield_plain_icon(shield)
    return emoji(emoji_id, fallback) if emoji_id else escape(fallback)


def shield_button_label(shield: Shield) -> str:
    name = shield.name
    return name if shield_emoji_id(shield) else f"{shield_plain_icon(shield)} {name}"
