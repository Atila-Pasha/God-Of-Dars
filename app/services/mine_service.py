from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_logic import (
    GameConfig,
    GameConfigurationError,
    MineLevel,
    game_config,
)
from app.models.mine import Mine
from app.models.resource import Resource
from app.models.user import User
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    MineLevelLocked,
    MineNotFound,
    MineUpgradeUnavailable,
    ResourceNotFound,
)


@dataclass(frozen=True)
class MineSnapshot:
    level: int
    production: MineLevel
    collected_minutes: int
    today_coin: int
    today_diamond: int
    today_banana: int


class MineService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config

    def _production(self, mine: Mine) -> MineLevel:
        try:
            return self.config.mine_level(mine.level)
        except GameConfigurationError as exc:
            raise MineNotFound from exc

    async def open(self, session: AsyncSession, user_id: int) -> MineSnapshot:
        user_result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user_result.scalar_one_or_none() is None:
            raise MineNotFound
        resources_result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        resources = resources_result.scalar_one_or_none()
        if resources is None:
            raise ResourceNotFound
        mine_result = await session.execute(
            select(Mine).where(Mine.user_id == user_id).with_for_update()
        )
        mine = mine_result.scalar_one_or_none()
        if mine is None:
            mine = Mine(user_id=user_id, last_collected_at=datetime.now(UTC))
            session.add(mine)
            await session.flush()
        collected_minutes = self._accrue(mine)
        await session.flush()
        return MineSnapshot(
            level=mine.level,
            production=self._production(mine),
            collected_minutes=collected_minutes,
            today_coin=mine.today_coin,
            today_diamond=mine.today_diamond,
            today_banana=mine.today_banana,
        )

    def _accrue(self, mine: Mine) -> int:
        now = datetime.now(UTC)
        last = mine.last_collected_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if mine.today != now.date():
            mine.today = now.date()
            mine.today_coin = mine.today_diamond = mine.today_banana = 0
        elapsed_minutes = max(0, int((now - last).total_seconds() // 60))
        elapsed_minutes = min(elapsed_minutes, self.config.mine_max_catchup_minutes)
        if elapsed_minutes == 0:
            return 0
        production = self._production(mine)
        amounts = (
            ("coin", production.coin_per_minute),
            ("diamond", production.diamond_per_minute),
            ("banana", production.banana_per_minute),
        )
        for field, rate in amounts:
            amount = rate * elapsed_minutes
            if amount == 0:
                continue
            setattr(mine, f"today_{field}", getattr(mine, f"today_{field}") + amount)
        mine.last_collected_at = last + timedelta(minutes=elapsed_minutes)
        return elapsed_minutes

    async def collect(
        self, session: AsyncSession, user_id: int
    ) -> tuple[MineSnapshot, tuple[int, int, int]]:
        user_result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user_result.scalar_one_or_none() is None:
            raise MineNotFound
        resources_result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        resources = resources_result.scalar_one_or_none()
        if resources is None:
            raise ResourceNotFound
        mine_result = await session.execute(
            select(Mine).where(Mine.user_id == user_id).with_for_update()
        )
        mine = mine_result.scalar_one_or_none()
        if mine is None:
            raise MineNotFound
        self._accrue(mine)
        amounts = (mine.today_coin, mine.today_diamond, mine.today_banana)
        ResourceService.credit_coin(
            session, resources, user_id=user_id, amount=amounts[0],
            reason="MINE_COLLECTION", reference_type="MINE", reference_id=mine.id,
        )
        ResourceService.credit_diamond(
            session, resources, user_id=user_id, amount=amounts[1],
            reason="MINE_COLLECTION", reference_type="MINE", reference_id=mine.id,
        )
        ResourceService.credit_banana(
            session, resources, user_id=user_id, amount=amounts[2],
            reason="MINE_COLLECTION", reference_type="MINE", reference_id=mine.id,
        )
        mine.today_coin = mine.today_diamond = mine.today_banana = 0
        await session.flush()
        return (
            MineSnapshot(
                level=mine.level,
                production=self._production(mine),
                collected_minutes=0,
                today_coin=0,
                today_diamond=0,
                today_banana=0,
            ),
            amounts,
        )

    async def upgrade(self, session: AsyncSession, user_id: int) -> MineSnapshot:
        user_result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise MineNotFound
        resources_result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        resources = resources_result.scalar_one_or_none()
        if resources is None:
            raise ResourceNotFound
        mine_result = await session.execute(
            select(Mine).where(Mine.user_id == user_id).with_for_update()
        )
        mine = mine_result.scalar_one_or_none()
        if mine is None:
            mine = Mine(user_id=user_id, last_collected_at=datetime.now(UTC))
            session.add(mine)
            await session.flush()
        collected_minutes = self._accrue(mine)
        try:
            next_level = self.config.mine_upgrade(mine.level, user.level)
        except GameConfigurationError as exc:
            message = str(exc)
            if "locked" in message.lower():
                raise MineLevelLocked from exc
            raise MineUpgradeUnavailable from exc
        ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=next_level.diamond_cost or 0,
            reason="MINE_UPGRADE",
            reference_type="MINE",
            reference_id=mine.id,
        )
        ResourceService.credit_banana(
            session,
            resources,
            user_id=user_id,
            amount=self.config.upgrade_banana_reward(next_level.diamond_cost or 0),
            reason="MINE_UPGRADE_XP",
            reference_type="MINE",
            reference_id=mine.id,
        )
        mine.level += 1
        await session.flush()
        return MineSnapshot(
            level=mine.level,
            production=self._production(mine),
            collected_minutes=collected_minutes,
            today_coin=mine.today_coin,
            today_diamond=mine.today_diamond,
            today_banana=mine.today_banana,
        )
