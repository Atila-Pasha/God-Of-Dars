import math
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_logic import GameConfig, GameConfigurationError, game_config
from app.models.castle import Castle
from app.repositories.castle import CastleRepository
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    CastleNotFound,
    CastleUpgradeUnavailable,
    InsufficientCoins,
    ResourceNotFound,
)
from app.services.shield_service import ShieldService


@dataclass(frozen=True)
class CastleSnapshot:
    level: int
    strength: int
    defense_power: int


@dataclass(frozen=True)
class CastleDamageResult:
    incoming_damage: int
    blocked_damage: int
    applied_damage: int
    castle_strength_before: int
    castle_strength_after: int


@dataclass(frozen=True)
class CastleRepairQuote:
    missing_strength: int
    diamond_cost: int


class CastleService:
    def __init__(
        self,
        repository: CastleRepository | None = None,
        *,
        config: GameConfig | None = None,
    ) -> None:
        self.repository = repository or CastleRepository()
        self.config = config or game_config
        self.shield_service = ShieldService(config=self.config)

    async def get_or_create(self, session: AsyncSession, user_id: int) -> Castle:
        castle = await self.repository.get_by_user(session, user_id)
        if castle is None:
            castle = await self.repository.create(
                session,
                user_id=user_id,
                strength=self.config.initial_castle_strength,
                defense_power=self.config.initial_defense_power,
            )
        elif castle.defense is None:
            from app.models.defense import Defense

            castle.defense = Defense(defense_power=self.config.initial_defense_power)
            await session.flush()
        return castle

    async def snapshot(self, session: AsyncSession, user_id: int) -> CastleSnapshot:
        castle = await self.get_or_create(session, user_id)
        if castle.defense is None:
            raise CastleNotFound
        return CastleSnapshot(
            level=castle.level,
            strength=castle.strength,
            defense_power=castle.defense.defense_power,
        )

    def can_upgrade(self, castle: Castle) -> bool:
        return self.can_upgrade_level(castle.level)

    def can_upgrade_level(self, castle_level: int) -> bool:
        try:
            self.config.castle_upgrade(castle_level)
        except GameConfigurationError:
            return False
        return True

    def repair_quote(self, castle: Castle) -> CastleRepairQuote:
        maximum = self.config.castle_max_strength(castle.level)
        missing = max(0, maximum - castle.strength)
        if missing == 0:
            return CastleRepairQuote(0, 0)
        rules = self.config.castle_repair
        cost = max(
            rules.minimum_diamond_cost,
            math.ceil(missing * rules.diamond_cost_per_100_strength / 100),
        )
        return CastleRepairQuote(missing, cost)

    async def repair(self, session: AsyncSession, user_id: int) -> Castle:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise CastleNotFound
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        castle = await self.repository.get_by_user(session, user_id, for_update=True)
        if castle is None or castle.defense is None:
            raise CastleNotFound
        quote = self.repair_quote(castle)
        if quote.missing_strength == 0:
            return castle
        ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=quote.diamond_cost,
            reason="CASTLE_REPAIR",
            reference_type="CASTLE",
            reference_id=castle.id,
        )
        castle.strength += quote.missing_strength
        await session.flush()
        return castle

    async def upgrade(self, session: AsyncSession, user_id: int) -> Castle:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise CastleNotFound

        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound

        castle = await self.repository.get_by_user(session, user_id, for_update=True)
        if castle is None:
            castle = await self.repository.create(
                session,
                user_id=user_id,
                strength=self.config.initial_castle_strength,
                defense_power=self.config.initial_defense_power,
            )
        if castle.defense is None:
            raise CastleNotFound

        try:
            upgrade = self.config.castle_upgrade(castle.level)
        except GameConfigurationError as exc:
            raise CastleUpgradeUnavailable from exc

        if resources.diamond < upgrade.diamond_cost:
            raise InsufficientCoins

        ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=upgrade.diamond_cost,
            reason="CASTLE_UPGRADE",
            reference_type="CASTLE",
            reference_id=castle.id,
        )
        ResourceService.credit_banana(
            session,
            resources,
            user_id=user_id,
            amount=self.config.upgrade_banana_reward(upgrade.diamond_cost),
            reason="CASTLE_UPGRADE_XP",
            reference_type="CASTLE",
            reference_id=castle.id,
        )
        castle.level += 1
        castle.strength += upgrade.strength_delta
        castle.defense.defense_power += upgrade.defense_delta
        await session.flush()
        return castle

    async def battle_snapshot(
        self, session: AsyncSession, user_id: int
    ) -> CastleSnapshot:
        return await self.snapshot(session, user_id)

    async def receive_attack_damage(
        self, session: AsyncSession, user_id: int, incoming_damage: int
    ) -> CastleDamageResult:
        """Apply incoming damage after consuming the equipped buffet shield."""
        castle = await self.repository.get_by_user(session, user_id, for_update=True)
        if castle is None:
            raise CastleNotFound
        mitigation = await self.shield_service.consume_for_attack(
            session, user_id, incoming_damage
        )
        before = castle.strength
        castle.strength = max(0, before - mitigation.remaining_damage)
        await session.flush()
        return CastleDamageResult(
            incoming_damage=mitigation.incoming_damage,
            blocked_damage=mitigation.blocked_damage,
            applied_damage=mitigation.remaining_damage,
            castle_strength_before=before,
            castle_strength_after=castle.strength,
        )
