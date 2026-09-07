from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.keyboards.daily import daily_keyboard
from app.services.daily_quest_service import DailyQuestService


class _Session:
    def __init__(self, progress):
        self.progress = progress

    async def scalar(self, _query):
        return self.progress

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_claim_is_atomic_and_second_claim_is_rejected():
    quest = SimpleNamespace(
        id=4,
        target=1,
        rewards={"COIN": 10, "DIAMOND": 2},
        quest_type="DAILY_LOGIN",
        is_active=True,
        activity_date=DailyQuestService.today(),
        quest_metadata={},
    )
    progress = SimpleNamespace(
        id=9, user_id=7, quest_id=4, progress=1, claimed=False, claimed_at=None
    )
    repository = SimpleNamespace(get=AsyncMock(return_value=quest))
    rewards = AsyncMock()
    rewards.grant.return_value = SimpleNamespace(created=True)
    service = DailyQuestService(repository=repository, reward_service=rewards)
    session = _Session(progress)

    assert await service.claim(session, user_id=7, progress_id=9) is progress
    assert progress.claimed is True
    assert rewards.grant.await_count == 2
    assert await service.claim(session, user_id=7, progress_id=9) is None


def test_empty_daily_keyboard_has_empty_state_action():
    markup = daily_keyboard([])
    assert markup.inline_keyboard
    assert markup.inline_keyboard[0][0].callback_data == "daily:noop"


def test_daily_quest_dates_are_explicit():
    service = DailyQuestService()
    assert service._date(date(2026, 9, 6)) == date(2026, 9, 6)


@pytest.mark.asyncio
async def test_join_channel_claim_requires_membership_checker():
    quest = SimpleNamespace(
        id=4,
        target=1,
        rewards={"COIN": 10},
        quest_type="JOIN_CHANNEL",
        is_active=True,
        activity_date=DailyQuestService.today(),
        quest_metadata={"channel": "@example"},
    )
    progress = SimpleNamespace(
        id=9, user_id=7, quest_id=4, progress=1, claimed=False, claimed_at=None
    )
    repository = SimpleNamespace(get=AsyncMock(return_value=quest))
    rewards = AsyncMock()
    service = DailyQuestService(repository=repository, reward_service=rewards)

    assert await service.claim(_Session(progress), user_id=7, progress_id=9) is None
    rewards.grant.assert_not_awaited()
