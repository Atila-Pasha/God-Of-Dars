from types import SimpleNamespace

import pytest

from app.repositories.leaderboard import LeaderboardRecord
from app.services.leaderboard_service import LeaderboardService


@pytest.mark.asyncio
async def test_leaderboard_assigns_ranks_and_caches_results() -> None:
    calls = 0

    class Repository:
        async def commanders(self, session, *, limit):
            nonlocal calls
            calls += 1
            assert limit == 10
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
