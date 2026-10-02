import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import NotificationStatus
from app.workers import notification_worker


class _Session:
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def begin(self):
        return self

    async def scalar(self, _query):
        return self.row


@pytest.mark.asyncio
async def test_completed_attack_launch_is_deleted_through_outbox(monkeypatch) -> None:
    row = SimpleNamespace(
        id=7,
        payload={"operation": "delete_message", "chat_id": -100123, "message_id": 44},
        attempts=1,
        status=NotificationStatus.PROCESSING,
        sent_at=None,
        next_attempt_at=None,
        last_error=None,
    )
    bot = SimpleNamespace(delete_message=AsyncMock(), send_message=AsyncMock())
    monkeypatch.setattr(notification_worker, "AsyncSessionLocal", lambda: _Session(row))

    await notification_worker._deliver_notification(bot, row, asyncio.Semaphore(1))

    bot.delete_message.assert_awaited_once_with(chat_id=-100123, message_id=44)
    bot.send_message.assert_not_awaited()
    assert row.status is NotificationStatus.SENT
