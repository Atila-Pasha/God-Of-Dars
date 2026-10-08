from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

_deletion_tasks: set[asyncio.Task[None]] = set()
_scheduled_deletions: set[tuple[int, int]] = set()


def group_user_request(message: Message) -> Message | None:
    """Return the user message a bot confirmation replied to in a group."""
    if message.chat.type not in {"group", "supergroup"}:
        return None
    source = message.reply_to_message
    if source is None or source.from_user is None or source.from_user.is_bot:
        return None
    return source


async def report_group_purchase_failure(
    callback: CallbackQuery,
    *,
    item_type: str,
    reason: str,
    source_message: Message | None,
) -> bool:
    """Post a failed purchase result in the group, linked to its command."""
    message = callback.message
    if not isinstance(message, Message) or message.chat.type not in {
        "group",
        "supergroup",
    }:
        return False
    with suppress(TelegramAPIError):
        await message.delete()
    try:
        await message.answer(
            f"❌ خرید {item_type} ناموفق بود.\nدلیل: {reason}",
            reply_to_message_id=(
                source_message.message_id if source_message is not None else None
            ),
            disable_group_reply=source_message is None,
        )
    except TelegramAPIError:
        return False
    return True


async def _delete_message_after(message: Message, delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)
    with suppress(TelegramAPIError):
        await message.delete()


def schedule_message_deletion(message: Message, *, delay_seconds: float = 10) -> None:
    """Delete a transient Telegram message without blocking its handler."""
    key = (message.chat.id, message.message_id)
    if key in _scheduled_deletions:
        return
    _scheduled_deletions.add(key)
    task = asyncio.create_task(
        _delete_message_after(message, delay_seconds),
        name=f"delete-telegram-message-{message.chat.id}-{message.message_id}",
    )
    _deletion_tasks.add(task)
    task.add_done_callback(_deletion_tasks.discard)
    task.add_done_callback(lambda _task: _scheduled_deletions.discard(key))


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
