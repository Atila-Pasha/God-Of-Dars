from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message

_deletion_tasks: set[asyncio.Task[None]] = set()


def group_user_request(message: Message) -> Message | None:
    """Return the user message a bot confirmation replied to in a group."""
    if message.chat.type not in {"group", "supergroup"}:
        return None
    source = message.reply_to_message
    if source is None or source.from_user is None or source.from_user.is_bot:
        return None
    return source


async def _delete_message_after(message: Message, delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)
    with suppress(TelegramAPIError):
        await message.delete()


def schedule_message_deletion(message: Message, *, delay_seconds: float = 10) -> None:
    """Delete a transient Telegram message without blocking its handler."""
    task = asyncio.create_task(
        _delete_message_after(message, delay_seconds),
        name=f"delete-telegram-message-{message.chat.id}-{message.message_id}",
    )
    _deletion_tasks.add(task)
    task.add_done_callback(_deletion_tasks.discard)


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
