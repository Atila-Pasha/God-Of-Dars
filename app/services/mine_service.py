from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import (
    GameConfig,
    GameConfigurationError,
    MineLevel,
    game_config,
)
from app.models.mine import Mine
from app.models.resource import Resource
from app.models.user import User
from app.services.daily_quest_service import DailyQuestService
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
    daily_produced_minutes: int = 0


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
            select(Resource)
            .where(Resource.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        resources = resources_result.scalar_one_or_none()
        if resources is None:
            raise ResourceNotFound
        mine = await self._get_or_create_mine(session, user_id, resources)
        collected_minutes = self._accrue(mine)
        await session.flush()
        return MineSnapshot(
            level=mine.level,
            production=self._production(mine),
            collected_minutes=collected_minutes,
            today_coin=mine.today_coin,
            today_diamond=mine.today_diamond,
            today_banana=mine.today_banana,
            daily_produced_minutes=mine.daily_produced_minutes or 0,
        )

    async def _get_or_create_mine(
        self, session: AsyncSession, user_id: int, resources: Resource
    ) -> Mine:
        # Callers lock the user first, serializing concurrent first opens.
        mine = await session.scalar(
            select(Mine).where(Mine.user_id == user_id).with_for_update()
        )
        if mine is not None:
            return mine
        mine = Mine(user_id=user_id, last_collected_at=datetime.now(UTC))
        session.add(mine)
        await session.flush()
        await ResourceService.credit_coin(
            session,
            resources,
            user_id=user_id,
            amount=100,
            reason="MINE_ACTIVATION_BONUS",
            reference_type="MINE",
            reference_id=mine.id,
        )
        return mine

    def _accrue(self, mine: Mine, *, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        last = mine.last_collected_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        limit = self.config.mine_max_catchup_minutes
        elapsed_minutes = max(0, int((now - last).total_seconds() // 60))
        capped = elapsed_minutes > limit
        elapsed_minutes = min(elapsed_minutes, limit)
        start = now - timedelta(minutes=elapsed_minutes) if capped else last
        end = start + timedelta(minutes=elapsed_minutes)
        midnight = datetime.combine(now.date(), time.min, tzinfo=UTC)
        today_minutes = min(
            elapsed_minutes,
            max(0, int((end - max(start, midnight)).total_seconds() // 60)),
        )
        previous_minutes = elapsed_minutes - today_minutes
        previous_used = (
            (mine.daily_produced_minutes or 0)
            if mine.today == start.date() and start.date() != now.date()
            else 0
        )
        previous_credit = min(previous_minutes, max(0, limit - previous_used))
        current_used = (
            (mine.daily_produced_minutes or 0) if mine.today == now.date() else 0
        )
        current_credit = min(today_minutes, max(0, limit - current_used))
        mine.today = now.date()
        # The today_* fields are uncollected cargo and persist across midnight.
        mine.daily_produced_minutes = current_used + current_credit
        credited_minutes = previous_credit + current_credit
        if elapsed_minutes == 0:
            return 0
        production = self._production(mine)
        amounts = (
            ("coin", production.coin_per_minute),
            ("diamond", production.diamond_per_minute),
            ("banana", production.banana_per_minute),
        )
        for field, rate in amounts:
            amount = rate * credited_minutes
            if amount == 0:
                continue
            setattr(mine, f"today_{field}", getattr(mine, f"today_{field}") + amount)
        # Discard old backlog once the catch-up ceiling is reached.
        mine.last_collected_at = now if capped or credited_minutes == 0 else end
        return credited_minutes

    async def collect(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        resource_type: ResourceType | None = None,
    ) -> tuple[MineSnapshot, tuple[int, int, int]]:
        user_result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user_result.scalar_one_or_none() is None:
            raise MineNotFound
        resources_result = await session.execute(
            select(Resource)
            .where(Resource.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
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
        if resource_type is ResourceType.COIN:
            # Banana production, if enabled later, is collected with gold.
            amounts = (mine.today_coin, 0, mine.today_banana)
        elif resource_type is ResourceType.DIAMOND:
            amounts = (0, mine.today_diamond, 0)
        elif resource_type is None:
            # Keep callbacks on messages sent by older bot versions usable.
            amounts = (mine.today_coin, mine.today_diamond, mine.today_banana)
        else:
            raise ValueError("Unsupported mine collection resource")
        credit_methods = (
            ResourceService.credit_coin,
            ResourceService.credit_diamond,
            ResourceService.credit_banana,
        )
        for amount, credit in zip(amounts, credit_methods, strict=True):
            if amount > 0:
                await credit(
                    session,
                    resources,
                    user_id=user_id,
                    amount=amount,
                    reason="MINE_COLLECTION",
                    reference_type="MINE",
                    reference_id=mine.id,
                )
        mine.today_coin -= amounts[0]
        mine.today_diamond -= amounts[1]
        mine.today_banana -= amounts[2]
        if any(amounts):
            mine.collection_count += 1
            await DailyQuestService().record_event(
                session,
                user_id=user_id,
                event_type="COLLECT_MINE",
                event_id=f"mine:{mine.id}:collection:{mine.collection_count}",
            )
        await session.flush()
        return (
            MineSnapshot(
                level=mine.level,
                production=self._production(mine),
                collected_minutes=0,
                today_coin=mine.today_coin,
                today_diamond=mine.today_diamond,
                today_banana=mine.today_banana,
                daily_produced_minutes=mine.daily_produced_minutes or 0,
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
            select(Resource)
            .where(Resource.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        resources = resources_result.scalar_one_or_none()
        if resources is None:
            raise ResourceNotFound
        mine = await self._get_or_create_mine(session, user_id, resources)
        collected_minutes = self._accrue(mine)
        try:
            next_level = self.config.mine_upgrade(mine.level, user.level)
        except GameConfigurationError as exc:
            message = str(exc)
            if "locked" in message.lower():
                raise MineLevelLocked from exc
            raise MineUpgradeUnavailable from exc
        await ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=next_level.diamond_cost or 0,
            reason="MINE_UPGRADE",
            reference_type="MINE",
            reference_id=mine.id,
        )
        await ResourceService.credit_banana(
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
            daily_produced_minutes=mine.daily_produced_minutes or 0,
        )
