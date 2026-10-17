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
from app.services.resource_service import ResourceService
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


def test_mine_cap_persists_across_days_without_collection() -> None:
    service = MineService(config=game_config)
    noon = datetime(2026, 10, 5, 12, tzinfo=UTC)
    cap = game_config.mine_max_catchup_minutes
    assert cap == 12 * 60
    mine = Mine(
        level=1,
        last_collected_at=noon - timedelta(minutes=10),
        today=noon.date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
        daily_produced_minutes=cap,
    )

    assert service._accrue(mine, now=noon) == 0
    assert mine.today_coin == 0
    assert mine.last_collected_at == noon

    tomorrow = noon + timedelta(days=1)
    assert service._accrue(mine, now=tomorrow) == 0
    assert mine.daily_produced_minutes == cap
    assert mine.today_coin == 0


def test_mine_cycle_cap_applies_across_repeated_opens() -> None:
    service = MineService(config=game_config)
    now = datetime(2026, 10, 5, 18, tzinfo=UTC)
    cap = game_config.mine_max_catchup_minutes
    mine = Mine(
        level=1,
        last_collected_at=now - timedelta(minutes=10),
        today=now.date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
        daily_produced_minutes=cap - 5,
    )
    assert service._accrue(mine, now=now) == 5
    assert service._accrue(mine, now=now + timedelta(minutes=10)) == 0
    assert mine.daily_produced_minutes == cap
    assert mine.today_coin == 5 * game_config.mine_level(1).coin_per_minute


def test_mine_keeps_producing_after_early_collection() -> None:
    service = MineService(config=game_config)
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    mine = Mine(
        level=1,
        last_collected_at=now - timedelta(minutes=1),
        today=now.date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
        daily_produced_minutes=0,
    )
    rate = game_config.mine_level(1).coin_per_minute

    assert service._accrue(mine, now=now) == 1
    assert mine.today_coin == rate
    mine.today_coin = 0  # The player collected the first minute's cargo.
    assert service._accrue(mine, now=now + timedelta(minutes=1)) == 1
    assert mine.today_coin == rate
    assert mine.daily_produced_minutes == 2


def test_mine_does_not_reset_at_tehran_midnight() -> None:
    service = MineService(config=game_config)
    # 20:30 UTC is 00:00 the next day in Tehran.
    now = datetime(2026, 10, 12, 20, 32, tzinfo=UTC)
    mine = Mine(
        level=1,
        last_collected_at=now - timedelta(minutes=4),
        today=(now - timedelta(hours=4)).date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
        daily_produced_minutes=game_config.mine_max_catchup_minutes,
    )

    assert service._accrue(mine, now=now) == 0
    assert mine.today == datetime(2026, 10, 13, tzinfo=UTC).date()
    assert mine.daily_produced_minutes == game_config.mine_max_catchup_minutes
    assert mine.today_coin == 0


def test_mine_does_not_start_new_cycle_before_utc_midnight() -> None:
    service = MineService(config=game_config)
    now = datetime(2026, 10, 12, 20, 55, tzinfo=UTC)
    mine = Mine(
        level=4,
        last_collected_at=now - timedelta(minutes=2),
        today=now.date(),
        today_coin=0,
        today_diamond=0,
        today_banana=0,
        daily_produced_minutes=game_config.mine_max_catchup_minutes,
    )

    assert service._accrue(mine, now=now) == 0
    assert mine.daily_produced_minutes == game_config.mine_max_catchup_minutes
    assert mine.today_coin == 0


@pytest.mark.asyncio
async def test_empty_full_mine_collection_restarts_without_daily_quest(
    monkeypatch,
) -> None:
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
        daily_produced_minutes=game_config.mine_max_catchup_minutes,
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

    snapshot, amounts = await MineService(config=game_config).collect(session, 1)

    assert amounts == (0, 0, 0)
    assert mine.collection_count == 0
    assert mine.daily_produced_minutes == 0
    assert snapshot.cycle_restarted is True
    record_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_mine_collects_gold_and_diamonds_independently(monkeypatch) -> None:
    mine = Mine(
        id=9,
        user_id=1,
        level=2,
        last_collected_at=datetime.now(UTC),
        today=datetime.now(UTC).date(),
        today_coin=100,
        today_diamond=20,
        today_banana=5,
        daily_produced_minutes=45,
        collection_count=0,
    )
    resources = Resource(user_id=1, coin=0, diamond=0, banana=0)

    def session():
        rows = iter(
            (
                SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=1)),
                SimpleNamespace(scalar_one_or_none=lambda: resources),
                SimpleNamespace(scalar_one_or_none=lambda: mine),
            )
        )
        return SimpleNamespace(
            execute=AsyncMock(side_effect=lambda statement: next(rows)),
            flush=AsyncMock(),
        )

    credit_coin = AsyncMock()
    credit_diamond = AsyncMock()
    credit_banana = AsyncMock()
    monkeypatch.setattr(ResourceService, "credit_coin", credit_coin)
    monkeypatch.setattr(ResourceService, "credit_diamond", credit_diamond)
    monkeypatch.setattr(ResourceService, "credit_banana", credit_banana)
    monkeypatch.setattr(DailyQuestService, "record_event", AsyncMock())
    service = MineService(config=game_config)

    snapshot, amounts = await service.collect(
        session(), 1, resource_type=ResourceType.COIN
    )
    assert amounts == (100, 0, 5)
    assert (snapshot.today_coin, snapshot.today_diamond, snapshot.today_banana) == (
        0,
        20,
        0,
    )
    assert snapshot.daily_produced_minutes == 45
    credit_coin.assert_awaited_once()
    credit_banana.assert_awaited_once()
    credit_diamond.assert_not_awaited()

    snapshot, amounts = await service.collect(
        session(), 1, resource_type=ResourceType.DIAMOND
    )
    assert amounts == (0, 20, 0)
    assert snapshot.today_diamond == 0
    assert snapshot.daily_produced_minutes == 45
    credit_diamond.assert_awaited_once()


@pytest.mark.asyncio
async def test_collecting_full_mine_starts_new_cycle_and_keeps_other_cargo(
    monkeypatch,
) -> None:
    cap = game_config.mine_max_catchup_minutes
    mine = Mine(
        id=9,
        user_id=1,
        level=2,
        last_collected_at=datetime.now(UTC) - timedelta(days=2),
        today_coin=100,
        today_diamond=20,
        today_banana=0,
        daily_produced_minutes=cap,
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
    monkeypatch.setattr(ResourceService, "credit_coin", AsyncMock())
    monkeypatch.setattr(DailyQuestService, "record_event", AsyncMock())

    snapshot, amounts = await MineService(config=game_config).collect(
        session, 1, resource_type=ResourceType.COIN
    )

    assert amounts == (100, 0, 0)
    assert snapshot.daily_produced_minutes == 0
    assert snapshot.today_diamond == 20
    assert mine.last_collected_at > datetime.now(UTC) - timedelta(minutes=1)
    assert (
        MineService(config=game_config)._accrue(
            mine, now=mine.last_collected_at + timedelta(minutes=10)
        )
        == 10
    )
    assert mine.daily_produced_minutes == 10
    assert mine.today_diamond == 20 + 10 * game_config.mine_level(2).diamond_per_minute


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
