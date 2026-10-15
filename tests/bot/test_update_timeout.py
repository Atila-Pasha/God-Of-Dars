import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import DeleteMessage

from app.bot.middlewares import database
from app.workers.game_message_cleanup import delete_game_message


@pytest.mark.asyncio
async def test_stuck_update_releases_its_database_transaction(monkeypatch) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(database.settings, "UPDATE_HANDLER_TIMEOUT_SECONDS", 0.01)

    async def stuck_handler(_event, _data):
        await asyncio.Event().wait()

    with pytest.raises(TimeoutError):
        await database.DatabaseSessionMiddleware()(stuck_handler, SimpleNamespace(), {})

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_kicked_group_deletion_is_not_retried_forever() -> None:
    bot = SimpleNamespace(
        delete_message=AsyncMock(
            side_effect=TelegramForbiddenError(
                DeleteMessage(chat_id=-100123, message_id=7),
                "bot was kicked from the supergroup chat",
            )
        )
    )

    assert await delete_game_message(bot, -100123, 7)
    bot.delete_message.assert_awaited_once_with(chat_id=-100123, message_id=7)
