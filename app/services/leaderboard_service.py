from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.leaderboard import LeaderboardRecord, LeaderboardRepository

LeaderboardKind = Literal["commander", "student", "fighter"]
LeaderboardPeriod = Literal["daily", "weekly", "monthly"]


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
            tuple[LeaderboardKind, LeaderboardPeriod, int, int],
            tuple[float, tuple[LeaderboardEntry, ...]],
        ] = {}
        self._cache_lock = asyncio.Lock()

    async def top(
        self,
        session: AsyncSession,
        kind: LeaderboardKind,
        *,
        period: LeaderboardPeriod = "weekly",
        limit: int = 10,
        now: datetime | None = None,
    ) -> tuple[LeaderboardEntry, ...]:
        if kind not in {"commander", "student", "fighter"}:
            raise ValueError("unsupported leaderboard kind")
        if period not in {"daily", "weekly", "monthly"}:
            raise ValueError("unsupported leaderboard period")
        if limit < 1 or limit > 50:
            raise ValueError("leaderboard limit must be between 1 and 50")

        since = self.period_start(period, now=now)
        cache_key = (kind, period, limit, int(since.timestamp()))
        cached = self._cache.get(cache_key)
        clock_now = monotonic()
        if cached is not None and cached[0] > clock_now:
            return cached[1]

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            clock_now = monotonic()
            if cached is not None and cached[0] > clock_now:
                return cached[1]
            records = await getattr(self.repository, f"{kind}s")(
                session,
                limit=limit,
                since=since,
            )
            entries = tuple(
                self._entry(rank, record)
                for rank, record in enumerate(records, start=1)
            )
            self._cache[cache_key] = (
                clock_now + self.cache_ttl_seconds,
                entries,
            )
            return entries

    async def position(
        self,
        session: AsyncSession,
        kind: LeaderboardKind,
        *,
        user_id: int,
        period: LeaderboardPeriod = "weekly",
        now: datetime | None = None,
    ) -> LeaderboardEntry | None:
        if kind not in {"commander", "student", "fighter"}:
            raise ValueError("unsupported leaderboard kind")
        if period not in {"daily", "weekly", "monthly"}:
            raise ValueError("unsupported leaderboard period")
        result = await getattr(self.repository, f"{kind}_position")(
            session,
            user_id=user_id,
            since=self.period_start(period, now=now),
        )
        if result is None:
            return None
        rank, record = result
        return self._entry(rank, record)

    @staticmethod
    def period_start(
        period: LeaderboardPeriod, *, now: datetime | None = None
    ) -> datetime:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        local = current.astimezone(ZoneInfo(settings.LEADERBOARD_TIMEZONE))
        if period == "daily":
            start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "weekly":
            # The Iranian calendar week starts on Saturday (weekday 5).
            days_since_saturday = (local.weekday() - 5) % 7
            start = (local - timedelta(days=days_since_saturday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif period == "monthly":
            start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            raise ValueError("unsupported leaderboard period")
        return start.astimezone(UTC)

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
