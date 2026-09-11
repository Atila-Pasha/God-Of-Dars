import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.utils.telegram import group_user_request, schedule_message_deletion


def test_group_user_request_returns_original_non_bot_message() -> None:
    source = SimpleNamespace(from_user=SimpleNamespace(is_bot=False))
    confirmation = SimpleNamespace(
        chat=SimpleNamespace(type="supergroup"),
        reply_to_message=source,
    )

    assert group_user_request(confirmation) is source


@pytest.mark.asyncio
async def test_scheduled_message_deletion_does_not_block() -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-100),
        message_id=21,
        delete=AsyncMock(),
    )

    schedule_message_deletion(message, delay_seconds=0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    message.delete.assert_awaited_once()
