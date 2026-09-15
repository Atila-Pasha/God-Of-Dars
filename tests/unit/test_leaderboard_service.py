from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.repositories.leaderboard import LeaderboardRecord
from app.services.leaderboard_service import LeaderboardService


@pytest.mark.asyncio
async def test_leaderboard_assigns_ranks_and_caches_results() -> None:
    calls = 0

    class Repository:
        async def commanders(self, session, *, limit, since):
            nonlocal calls
            calls += 1
            assert limit == 10
            assert since.tzinfo is not None
            return [
                LeaderboardRecord(7, "علی", None, "ali", 12, 80),
                LeaderboardRecord(8, "سارا", "احمدی", None, 10, 20),
            ]

    service = LeaderboardService(Repository(), cache_ttl_seconds=60)

    first = await service.top(SimpleNamespace(), "commander")
    second = await service.top(SimpleNamespace(), "commander")

    assert calls == 1
    assert second == first
    assert first[0].rank == 1
    assert first[0].name == "علی"
    assert first[1].rank == 2
    assert first[1].name == "سارا احمدی"


@pytest.mark.asyncio
async def test_leaderboard_rejects_invalid_limits() -> None:
    service = LeaderboardService(SimpleNamespace())

    with pytest.raises(ValueError):
        await service.top(SimpleNamespace(), "commander", limit=0)


@pytest.mark.asyncio
async def test_leaderboard_returns_viewer_position() -> None:
    record = LeaderboardRecord(7, "علی", None, "ali", 12, 80)

    class Repository:
        async def commander_position(self, session, *, user_id, since):
            assert user_id == 7
            assert since.tzinfo is not None
            return 30, record

    service = LeaderboardService(Repository())

    entry = await service.position(SimpleNamespace(), "commander", user_id=7)

    assert entry is not None
    assert entry.rank == 30
    assert entry.username == "ali"


def test_leaderboard_periods_use_tehran_calendar_boundaries() -> None:
    now = datetime(2026, 9, 16, 8, 30, tzinfo=UTC)

    assert LeaderboardService.period_start("daily", now=now) == datetime(
        2026, 9, 15, 20, 30, tzinfo=UTC
    )
    assert LeaderboardService.period_start("weekly", now=now) == datetime(
        2026, 9, 11, 20, 30, tzinfo=UTC
    )
    assert LeaderboardService.period_start("monthly", now=now) == datetime(
        2026, 8, 31, 20, 30, tzinfo=UTC
    )
