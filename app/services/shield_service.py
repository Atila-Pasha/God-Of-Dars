from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ResourceType
from app.core.game_logic import (
    GameConfig,
    GameConfigurationError,
    ShieldMitigation,
    game_config,
)
from app.models.resource import Resource
from app.models.shield import Shield
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_shield import UserShield
from app.services.school_errors import (
    InsufficientCoins,
    ResourceNotFound,
    ShieldLocked,
    ShieldNotFound,
    ShieldNotPurchasable,
)


@dataclass(frozen=True)
class ShieldPurchase:
    shield: Shield
    quantity: int
    equipped: bool


class ShieldService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config

    async def catalog(
        self, session: AsyncSession, *, player_level: int
    ) -> list[Shield]:
        result = await session.execute(
            select(Shield)
            .where(Shield.is_active.is_(True), Shield.unlock_level <= player_level)
            .order_by(Shield.unlock_level, Shield.id)
        )
        return list(result.scalars().all())

    async def list_owned(self, session: AsyncSession, user_id: int) -> list[UserShield]:
        result = await session.execute(
            select(UserShield)
            .where(UserShield.user_id == user_id, UserShield.quantity > 0)
            .options(selectinload(UserShield.shield))
            .order_by(UserShield.is_equipped.desc(), UserShield.id)
        )
        return list(result.scalars().unique().all())

    async def get_shield(self, session: AsyncSession, shield_id: int) -> Shield | None:
        result = await session.execute(select(Shield).where(Shield.id == shield_id))
        return result.scalar_one_or_none()

    def validate(self, shield: Shield) -> None:
        try:
            self.config.apply_shield(
                1,
                reduction_percent=shield.reduction_percent,
                flat_absorption=shield.flat_absorption,
            )
        except GameConfigurationError as exc:
            raise ShieldNotPurchasable from exc
        if shield.purchase_price < 0 or shield.unlock_level < 1:
            raise ShieldNotPurchasable

    async def buy(
        self, session: AsyncSession, user_id: int, shield_id: int
    ) -> ShieldPurchase:
        user_result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise ShieldNotFound
        resource_result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        resources = resource_result.scalar_one_or_none()
        if resources is None:
            raise ResourceNotFound
        shield_result = await session.execute(
            select(Shield).where(Shield.id == shield_id).with_for_update()
        )
        shield = shield_result.scalar_one_or_none()
        if shield is None:
            raise ShieldNotFound
        if not shield.is_active:
            raise ShieldNotPurchasable
        if user.level < shield.unlock_level:
            raise ShieldLocked
        self.validate(shield)
        if resources.coin < shield.purchase_price:
            raise InsufficientCoins

        owned_result = await session.execute(
            select(UserShield)
            .where(UserShield.user_id == user_id, UserShield.shield_id == shield_id)
            .with_for_update()
        )
        owned = owned_result.scalar_one_or_none()
        if owned is None:
            owned = UserShield(user_id=user_id, shield_id=shield_id, quantity=0)
            session.add(owned)
            await session.flush()
        owned.quantity += 1
        equipped = False
        active_result = await session.execute(
            select(UserShield).where(
                UserShield.user_id == user_id,
                UserShield.is_equipped.is_(True),
                UserShield.quantity > 0,
            )
        )
        if active_result.scalar_one_or_none() is None:
            owned.is_equipped = True
            equipped = True
        before = resources.coin
        resources.coin -= shield.purchase_price
        session.add(
            Transaction(
                user_id=user_id,
                resource_type=ResourceType.COIN,
                amount=-shield.purchase_price,
                balance_before=before,
                balance_after=resources.coin,
                reason="SHIELD_PURCHASE",
                reference_type="USER_SHIELD",
                reference_id=owned.id,
            )
        )
        await session.flush()
        owned.shield = shield
        return ShieldPurchase(shield=shield, quantity=owned.quantity, equipped=equipped)

    async def equip(
        self, session: AsyncSession, user_id: int, user_shield_id: int
    ) -> UserShield:
        result = await session.execute(
            select(UserShield)
            .where(UserShield.id == user_shield_id, UserShield.user_id == user_id)
            .options(selectinload(UserShield.shield))
            .with_for_update()
        )
        selected = result.scalar_one_or_none()
        if selected is None or selected.quantity <= 0:
            raise ShieldNotFound
        await session.execute(
            UserShield.__table__.update()
            .where(UserShield.user_id == user_id)
            .values(is_equipped=False)
        )
        selected.is_equipped = True
        await session.flush()
        return selected

    async def consume_for_attack(
        self, session: AsyncSession, user_id: int, incoming_damage: int
    ) -> ShieldMitigation:
        """Apply and consume the equipped shield for one incoming attack.

        The attack resolver should call this immediately before applying damage
        to the castle. Returning a pure ``ShieldMitigation`` keeps the formula
        in game_logic and makes the worker easy to test.
        """
        if incoming_damage < 0:
            raise GameConfigurationError("Incoming damage cannot be negative")
        result = await session.execute(
            select(UserShield)
            .where(
                UserShield.user_id == user_id,
                UserShield.is_equipped.is_(True),
                UserShield.quantity > 0,
            )
            .options(selectinload(UserShield.shield))
            .with_for_update()
        )
        equipped = result.scalar_one_or_none()
        if equipped is None:
            return ShieldMitigation(incoming_damage, 0, incoming_damage)
        self.validate(equipped.shield)
        mitigation = self.config.apply_shield(
            incoming_damage,
            reduction_percent=equipped.shield.reduction_percent,
            flat_absorption=equipped.shield.flat_absorption,
        )
        equipped.quantity -= 1
        if equipped.quantity == 0:
            equipped.is_equipped = False
        await session.flush()
        return mitigation


class ShieldAdminService:
    """CRUD for the shield catalog used by the private admin bot."""

    async def list_shields(self, session: AsyncSession) -> list[Shield]:
        result = await session.execute(select(Shield).order_by(Shield.id))
        return list(result.scalars().all())

    async def get_shield(self, session: AsyncSession, shield_id: int) -> Shield | None:
        result = await session.execute(
            select(Shield)
            .where(Shield.id == shield_id)
            .options(selectinload(Shield.owned_by_users))
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _validate(values: dict[str, object]) -> None:
        name = str(values.get("name", "")).strip()
        if not name:
            raise ValueError("shield name cannot be empty")
        if not 0 <= int(values.get("reduction_percent", -1)) <= 100:
            raise ValueError("reduction_percent must be between 0 and 100")
        if int(values.get("flat_absorption", -1)) < 0:
            raise ValueError("flat_absorption cannot be negative")
        if int(values.get("purchase_price", -1)) < 0:
            raise ValueError("purchase_price cannot be negative")
        if int(values.get("unlock_level", 0)) < 1:
            raise ValueError("unlock_level must be positive")

    async def create_shield(self, session: AsyncSession, **values: object) -> Shield:
        self._validate(values)
        values["name"] = str(values["name"]).strip()
        shield = Shield(**values)
        session.add(shield)
        await session.flush()
        return shield

    async def update_shield(
        self, session: AsyncSession, shield_id: int, **values: object
    ) -> Shield | None:
        shield = await self.get_shield(session, shield_id)
        if shield is None:
            return None
        merged = {
            "name": values.get("name", shield.name),
            "reduction_percent": values.get(
                "reduction_percent", shield.reduction_percent
            ),
            "flat_absorption": values.get("flat_absorption", shield.flat_absorption),
            "purchase_price": values.get("purchase_price", shield.purchase_price),
            "unlock_level": values.get("unlock_level", shield.unlock_level),
        }
        self._validate(merged)
        for key, value in values.items():
            setattr(shield, key, str(value).strip() if key == "name" else value)
        await session.flush()
        return shield

    async def delete_shield(
        self, session: AsyncSession, shield_id: int
    ) -> tuple[bool, Shield | None]:
        shield = await self.get_shield(session, shield_id)
        if shield is None:
            return False, None
        if shield.owned_by_users:
            shield.is_active = False
            await session.flush()
            return False, shield
        await session.delete(shield)
        await session.flush()
        return True, shield
