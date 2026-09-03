from __future__ import annotations

from typing import Any

from aiogram.exceptions import TelegramBadRequest


async def safe_edit_text(message: Any, text: str, **kwargs: Any) -> bool:
    """Edit a message without failing when Telegram sees no visual change."""
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise
    return True


async def safe_edit_reply_markup(message: Any, **kwargs: Any) -> bool:
    """Remove/update markup while tolerating an already identical markup."""
    try:
        await message.edit_reply_markup(**kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise
    return True
