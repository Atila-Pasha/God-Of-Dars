from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.bot.custom_emojis import _send_message_with_reply_fallback
from app.bot.handlers.buffet import invalid_shield_purchase_message


@pytest.mark.asyncio
async def test_bare_shield_purchase_requires_a_name() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await invalid_shield_purchase_message(message)

    message.answer.assert_awaited_once_with("فرمت صحیح: خرید سپر {اسم سپر}")


@pytest.mark.asyncio
async def test_stale_group_reply_is_retried_without_reply_target() -> None:
    sender = AsyncMock(
        side_effect=[
            TelegramBadRequest(
                method=SimpleNamespace(),
                message="Bad Request: message to be replied not found",
            ),
            "sent",
        ]
    )
    kwargs = {"chat_id": -100, "text": "خرید انجام شد", "reply_to_message_id": 42}

    result = await _send_message_with_reply_fallback(
        sender, SimpleNamespace(), (), kwargs
    )

    assert result == "sent"
    assert "reply_to_message_id" not in kwargs
    assert sender.await_count == 2
