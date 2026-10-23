from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.rank_service import (
    DAILY_LIMIT,
    TIERS,
    RankService,
    local_date,
    match_tier_order,
    season_start,
    tier_for,
)
from app.services.resource_service import ResourceService
from app.services.school_errors import RankDailyLimitReached


@pytest.mark.parametrize(
    ("cups", "name"),
    [
        (0, "مبتدی"),
        (200, "مبتدی"),
        (201, "برنزی"),
        (600, "برنزی"),
        (601, "نقره‌ای"),
        (1000, "نقره‌ای"),
        (1001, "طلایی"),
        (1400, "طلایی"),
        (1401, "سوپر طلایی"),
        (1801, "دیاموندی"),
        (2201, "پلاتینیومی"),
        (2601, "فرمانده"),
        (9999, "فرمانده"),
    ],
)
def test_rank_boundaries_have_no_gaps(cups, name) -> None:
    assert tier_for(cups).name == name


def test_monthly_reset_starts_first_day_in_tehran() -> None:
    # October 31 at 20:29 UTC is still October in Tehran.
    before = datetime(2026, 10, 31, 20, 29, tzinfo=UTC)
    after = before + timedelta(minutes=2)
    assert season_start(after) > season_start(before)
    assert local_date(after) > local_date(before)


@pytest.mark.asyncio
async def test_ranked_daily_limit_counts_commands_once(monkeypatch) -> None:
    now = datetime(2026, 10, 22, 8, tzinfo=UTC)
    profile = SimpleNamespace(daily_date=local_date(now), daily_attacks=19)
    monkeypatch.setattr(RankService, "locked_profile", AsyncMock(return_value=profile))
    session = SimpleNamespace()
    user = SimpleNamespace(id=1)
    await RankService.reserve_attack(session, user, now=now)
    assert profile.daily_attacks == DAILY_LIMIT
    with pytest.raises(RankDailyLimitReached):
        await RankService.reserve_attack(session, user, now=now)
    assert profile.daily_attacks == DAILY_LIMIT


@pytest.mark.asyncio
async def test_rank_result_is_settled_once_for_multi_teacher_command(
    monkeypatch,
) -> None:
    attacker = SimpleNamespace(id=1)
    defender = SimpleNamespace(id=2)
    a_rank = SimpleNamespace(cups=601, best_cups=601, wins=0, losses=0)
    d_rank = SimpleNamespace(cups=620, best_cups=620, wins=0, losses=0)
    coin = AsyncMock()
    banana = AsyncMock()
    monkeypatch.setattr(ResourceService, "credit_coin", coin)
    monkeypatch.setattr(ResourceService, "credit_banana", banana)
    monkeypatch.setattr(
        RankService, "locked_profile", AsyncMock(side_effect=[a_rank, d_rank])
    )
    rows = [
        SimpleNamespace(id=11, is_ranked=True, rank_settled=False, is_successful=True),
        SimpleNamespace(id=12, is_ranked=True, rank_settled=False, is_successful=True),
    ]
    result = await RankService.settle_command(
        SimpleNamespace(), rows, attacker, defender
    )
    assert result is not None and result.delta[0] > 0 and result.delta[1] < 0
    assert result.reward == (50, 2, 0)
    assert coin.await_count == banana.await_count == 1
    assert coin.await_args.kwargs["reference_id"] == 11
    assert a_rank.wins == d_rank.losses == 1
    assert rows[0].rank_settled
    assert (
        await RankService.settle_command(SimpleNamespace(), rows, attacker, defender)
        is None
    )
    assert a_rank.wins == 1
    assert coin.await_count == banana.await_count == 1


@pytest.mark.asyncio
async def test_old_season_pays_reward_once_and_resets(monkeypatch) -> None:
    from app.services.notification_service import NotificationService

    coin = AsyncMock()
    banana = AsyncMock()
    diamond = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(ResourceService, "credit_coin", coin)
    monkeypatch.setattr(ResourceService, "credit_banana", banana)
    monkeypatch.setattr(ResourceService, "credit_diamond", diamond)
    monkeypatch.setattr(NotificationService, "enqueue", notify)
    now = datetime(2026, 11, 1, 9, tzinfo=UTC)
    old = season_start(now - timedelta(days=1))
    profile = SimpleNamespace(
        season_start=old,
        cups=2201,
        best_cups=2300,
        wins=15,
        losses=2,
        daily_date=None,
        daily_attacks=10,
    )
    user = SimpleNamespace(id=7, telegram_user_id=700, resources=object())
    session = SimpleNamespace(scalar=AsyncMock(return_value=profile))
    await RankService.locked_profile(session, user, now=now)
    await RankService.locked_profile(session, user, now=now)
    assert profile.cups == profile.best_cups == profile.wins == profile.losses == 0
    assert profile.season_start == season_start(now)
    assert coin.await_count == banana.await_count == diamond.await_count == 1
    assert coin.await_args.kwargs["amount"] == 280
    assert banana.await_args.kwargs["amount"] == 12
    assert diamond.await_args.kwargs["amount"] == 7
    assert notify.await_count == 1


@pytest.mark.parametrize(
    ("own", "expected"),
    [
        (0, (0, 1, 2, 3, 4, 5, 6, 7)),
        (2, (2, 3, 4, 5, 6, 7, 1, 0)),
        (7, (7, 6, 5, 4, 3, 2, 1, 0)),
    ],
)
def test_match_tier_order_checks_all_real_tiers(own, expected) -> None:
    assert len(expected) == len(TIERS)
    assert match_tier_order(own) == expected


@pytest.mark.asyncio
async def test_far_tier_real_opponent_loses_cups(monkeypatch) -> None:
    attacker = SimpleNamespace(id=1)
    defender = SimpleNamespace(id=2)
    profile = SimpleNamespace(cups=201, best_cups=201, wins=0, losses=0)
    defender_profile = SimpleNamespace(cups=2601, best_cups=2601, wins=0, losses=0)
    locked = AsyncMock(side_effect=[profile, defender_profile])
    coin = AsyncMock()
    monkeypatch.setattr(RankService, "locked_profile", locked)
    monkeypatch.setattr(ResourceService, "credit_coin", coin)
    attack = SimpleNamespace(
        id=15, is_ranked=True, rank_settled=False, is_successful=True
    )

    result = await RankService.settle_command(
        SimpleNamespace(), [attack], attacker, defender
    )

    assert result is not None and result.delta[0] > 0 and result.delta[1] < 0
    assert result.reward == (20, 0, 0)
    assert locked.await_count == 2
    assert defender_profile.cups < 2601 and defender_profile.losses == 1
    coin.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_ranked_attack_still_pays_its_tier_once(monkeypatch) -> None:
    attacker = SimpleNamespace(id=1)
    defender = SimpleNamespace(id=2)
    attacker_profile = SimpleNamespace(cups=300, best_cups=300, wins=0, losses=0)
    defender_profile = SimpleNamespace(cups=320, best_cups=320, wins=0, losses=0)
    monkeypatch.setattr(
        RankService,
        "locked_profile",
        AsyncMock(side_effect=[attacker_profile, defender_profile]),
    )
    credit = AsyncMock()
    monkeypatch.setattr(ResourceService, "credit_coin", credit)
    attack = SimpleNamespace(
        id=16, is_ranked=True, rank_settled=False, is_successful=False
    )

    result = await RankService.settle_command(
        SimpleNamespace(), [attack], attacker, defender
    )

    assert result is not None and result.delta == (-8, 0)
    assert result.reward == (20, 0, 0)
    assert attacker_profile.losses == 1 and defender_profile.losses == 0
    credit.assert_awaited_once()
