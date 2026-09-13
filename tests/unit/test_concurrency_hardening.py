from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import AttackStatus, ResourceType
from app.core.game_logic import game_config
from app.models.mine import Mine
from app.models.resource import Resource
from app.services.daily_quest_service import DailyQuestService
from app.services.mine_service import MineService
from app.services.reward_service import RewardService, RewardSpec


def test_attack_state_machine_has_processing_and_failed_states() -> None:
    assert AttackStatus.PROCESSING.value == "PROCESSING"
    assert AttackStatus.FAILED.value == "FAILED"


def test_mine_discards_backlog_beyond_catchup_cap() -> None:
    now = datetime.now(UTC)
    mine = Mine(
        level=1,
        last_collected_at=now - timedelta(hours=48),
        today=now.date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
    )

    MineService(config=game_config)._accrue(mine)

    assert mine.last_collected_at >= now - timedelta(minutes=1)


def test_mine_keeps_uncollected_balance_across_midnight() -> None:
    now = datetime.now(UTC)
    mine = Mine(
        level=1,
        last_collected_at=now - timedelta(minutes=2),
        today=(now - timedelta(days=1)).date(),
        today_coin=50,
        today_diamond=3,
        today_banana=1,
    )

    MineService(config=game_config)._accrue(mine)

    assert mine.today_coin >= 54
    assert mine.today_diamond == 3
    assert mine.today_banana == 1


@pytest.mark.asyncio
async def test_empty_mine_collection_does_not_advance_daily_quest(monkeypatch) -> None:
    now = datetime.now(UTC)
    mine = Mine(
        id=9,
        user_id=1,
        level=1,
        last_collected_at=now,
        today=now.date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
        collection_count=0,
    )
    rows = iter(
        (
            SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=1)),
            SimpleNamespace(
                scalar_one_or_none=lambda: Resource(
                    user_id=1, coin=0, diamond=0, banana=0
                )
            ),
            SimpleNamespace(scalar_one_or_none=lambda: mine),
        )
    )
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=lambda statement: next(rows)),
        flush=AsyncMock(),
    )
    record_event = AsyncMock()
    monkeypatch.setattr(DailyQuestService, "record_event", record_event)

    _, amounts = await MineService(config=game_config).collect(session, 1)

    assert amounts == (0, 0, 0)
    assert mine.collection_count == 0
    record_event.assert_not_awaited()


class _RewardSession:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.resources = Resource(coin=0, diamond=0, banana=0)

    async def execute(self, statement):
        self.events.append("resource_lock")
        return SimpleNamespace(scalar_one_or_none=lambda: self.resources)

    def add(self, value) -> None:
        self.events.append("add")

    async def flush(self) -> None:
        self.events.append("flush")


class _RewardRepository:
    async def get_by_reference(self, session, **kwargs):
        session.events.append("idempotency_check")
        return None


@pytest.mark.asyncio
async def test_reward_locks_balance_before_idempotency_check() -> None:
    session = _RewardSession()
    service = RewardService(_RewardRepository())

    await service.grant(
        session,
        user_id=1,
        spec=RewardSpec(ResourceType.COIN, 1),
        source="TEST",
        reference_type="EVENT",
        reference_id=1,
    )

    assert session.events.index("resource_lock") < session.events.index(
        "idempotency_check"
    )
