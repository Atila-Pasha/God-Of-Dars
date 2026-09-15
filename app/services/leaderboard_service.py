from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.leaderboard import LeaderboardRecord, LeaderboardRepository

LeaderboardKind = Literal["commander", "student", "fighter"]


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    user_id: int
    name: str
    username: str | None
    primary_value: int
    secondary_value: int


class LeaderboardService:
    def __init__(
        self,
        repository: LeaderboardRepository | None = None,
        *,
        cache_ttl_seconds: float = 20.0,
    ) -> None:
        self.repository = repository or LeaderboardRepository()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[
            tuple[LeaderboardKind, int], tuple[float, tuple[LeaderboardEntry, ...]]
        ] = {}
        self._cache_lock = asyncio.Lock()

    async def top(
        self,
        session: AsyncSession,
        kind: LeaderboardKind,
        *,
        limit: int = 10,
    ) -> tuple[LeaderboardEntry, ...]:
        if kind not in {"commander", "student", "fighter"}:
            raise ValueError("unsupported leaderboard kind")
        if limit < 1 or limit > 50:
            raise ValueError("leaderboard limit must be between 1 and 50")

        cache_key = (kind, limit)
        cached = self._cache.get(cache_key)
        now = monotonic()
        if cached is not None and cached[0] > now:
            return cached[1]

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            now = monotonic()
            if cached is not None and cached[0] > now:
                return cached[1]
            records = await getattr(self.repository, f"{kind}s")(session, limit=limit)
            entries = tuple(
                self._entry(rank, record)
                for rank, record in enumerate(records, start=1)
            )
            self._cache[cache_key] = (now + self.cache_ttl_seconds, entries)
            return entries

    @staticmethod
    def _entry(rank: int, record: LeaderboardRecord) -> LeaderboardEntry:
        name = " ".join(
            part.strip()
            for part in (record.first_name, record.last_name)
            if part and part.strip()
        )
        return LeaderboardEntry(
            rank=rank,
            user_id=record.user_id,
            name=name or "فرمانده بی‌نام",
            username=record.username,
            primary_value=record.primary_value,
            secondary_value=record.secondary_value,
        )
