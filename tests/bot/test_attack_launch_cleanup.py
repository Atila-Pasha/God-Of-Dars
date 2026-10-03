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


@pytest.mark.asyncio
async def test_teacher_injury_report_waits_for_battle_report(monkeypatch) -> None:
    row = SimpleNamespace(
        id=8,
        payload={
            "chat_id": 42,
            "text": "گزارش آسیب دبیر",
            "depends_on_key": "ATTACK_RESULT:7:ATTACKER",
        },
        attempts=1,
        status=NotificationStatus.PROCESSING,
        processing_at=None,
        next_attempt_at=None,
    )

    class _DependencySession(_Session):
        def __init__(self):
            super().__init__(row)
            self.lookups = 0

        async def scalar(self, _query):
            self.lookups += 1
            return NotificationStatus.PROCESSING if self.lookups == 1 else row

    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(notification_worker, "AsyncSessionLocal", _DependencySession)

    await notification_worker._deliver_notification(bot, row, asyncio.Semaphore(1))

    bot.send_message.assert_not_awaited()
    assert row.status is NotificationStatus.PENDING
    assert row.attempts == 0
    assert row.next_attempt_at is not None


@pytest.mark.asyncio
async def test_teacher_injury_report_sends_after_battle_report(monkeypatch) -> None:
    row = SimpleNamespace(
        id=9,
        payload={
            "chat_id": 42,
            "text": "گزارش آسیب دبیر",
            "parse_mode": "MarkdownV2",
            "depends_on_key": "ATTACK_RESULT:7:ATTACKER",
        },
        attempts=1,
        status=NotificationStatus.PROCESSING,
        sent_at=None,
        next_attempt_at=None,
        last_error=None,
    )

    lookups = 0

    class _DependencySession(_Session):
        async def scalar(self, _query):
            nonlocal lookups
            lookups += 1
            return NotificationStatus.SENT if lookups == 1 else row

    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(
        notification_worker, "AsyncSessionLocal", lambda: _DependencySession(row)
    )

    await notification_worker._deliver_notification(bot, row, asyncio.Semaphore(1))

    bot.send_message.assert_awaited_once_with(
        chat_id=42, text="گزارش آسیب دبیر", parse_mode="MarkdownV2"
    )
    assert row.status is NotificationStatus.SENT
