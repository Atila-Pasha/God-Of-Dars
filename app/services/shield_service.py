from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
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
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    InsufficientCoins,
    InsufficientDiamonds,
    ResourceNotFound,
    ShieldAlreadyActive,
    ShieldLocked,
    ShieldNotFound,
    ShieldNotPurchasable,
)


@dataclass(frozen=True)
class ShieldPurchase:
    shield: Shield
    active_until: datetime


SHIELD_DAY_TIMEZONE = ZoneInfo("Asia/Tehran")


class ShieldDailyLimitReached(Exception):
    pass


class ShieldService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config

    async def catalog(
        self, session: AsyncSession, *, player_level: int | None
    ) -> list[Shield]:
        statement = select(Shield).where(Shield.is_active.is_(True))
        if player_level is not None:
            statement = statement.where(Shield.unlock_level <= player_level)
        result = await session.execute(
            statement.order_by(Shield.unlock_level, Shield.id)
        )
        return list(result.scalars().all())

    async def list_owned(self, session: AsyncSession, user_id: int) -> list[UserShield]:
        now = datetime.now(UTC)
        result = await session.execute(
            select(UserShield)
            .where(
                UserShield.user_id == user_id,
                UserShield.active_until.is_not(None),
                UserShield.active_until > now,
            )
            .options(selectinload(UserShield.shield))
            .order_by(UserShield.is_equipped.desc(), UserShield.id)
        )
        return list(result.scalars().unique().all())

    @staticmethod
    def _kazemi_bypassed(shield: Shield, teacher_names: tuple[str, ...] | None) -> bool:
        return shield.name == "سپر کاظمی" and (
            teacher_names is None
            or any("موسوی" in name or "قلمچی" in name for name in teacher_names)
        )

    async def has_active_shield(
        self,
        session: AsyncSession,
        user_id: int,
        teacher_names: tuple[str, ...] | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        result = await session.execute(
            select(UserShield)
            .where(
                UserShield.user_id == user_id,
                UserShield.active_until.is_not(None),
                UserShield.active_until > now,
            )
            .options(selectinload(UserShield.shield))
            .order_by(UserShield.is_equipped.desc(), UserShield.id)
            .limit(1)
        )
        active = result.scalar_one_or_none()
        return active is not None and not self._kazemi_bypassed(
            active.shield, teacher_names
        )

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
        if (
            shield.purchase_price < 0
            or shield.unlock_level < 1
            or shield.duration_minutes < 1
        ):
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
            select(Resource)
            .where(Resource.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
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
        owned_result = await session.execute(
            select(UserShield)
            .where(UserShield.user_id == user_id)
            .options(selectinload(UserShield.shield))
            .with_for_update()
        )
        owned_items = list(owned_result.scalars().all())
        now = datetime.now(UTC)
        if any(
            item.active_until is not None and item.active_until > now
            for item in owned_items
        ):
            raise ShieldAlreadyActive
        daily_limit = shield.daily_limit
        if daily_limit is not None:
            local_day = now.astimezone(SHIELD_DAY_TIMEZONE).date()
            day_start = datetime.combine(
                local_day, datetime.min.time(), SHIELD_DAY_TIMEZONE
            ).astimezone(UTC)
            day_end = (
                datetime.combine(local_day, datetime.min.time(), SHIELD_DAY_TIMEZONE)
                + timedelta(days=1)
            ).astimezone(UTC)
            purchase_count = await session.scalar(
                select(func.count(Transaction.id))
                .join(UserShield, Transaction.reference_id == UserShield.id)
                .where(
                    Transaction.user_id == user_id,
                    Transaction.reason == "SHIELD_PURCHASE",
                    Transaction.reference_type == "USER_SHIELD",
                    UserShield.shield_id == shield_id,
                    Transaction.created_at >= day_start,
                    Transaction.created_at < day_end,
                )
            )
            if (purchase_count or 0) >= daily_limit:
                raise ShieldDailyLimitReached
        balance = getattr(resources, shield.purchase_resource.value.lower())
        if balance < shield.purchase_price:
            if shield.purchase_resource is ResourceType.DIAMOND:
                raise InsufficientDiamonds
            raise InsufficientCoins
        owned = next(
            (item for item in owned_items if item.shield_id == shield_id), None
        )
        if owned is None:
            owned = UserShield(user_id=user_id, shield_id=shield_id, quantity=0)
            session.add(owned)
            await session.flush()
        owned.quantity = 1
        owned.is_equipped = True
        owned.active_until = now + timedelta(minutes=shield.duration_minutes)
        await ResourceService.debit(
            session,
            resources,
            user_id=user_id,
            resource_type=shield.purchase_resource,
            amount=shield.purchase_price,
            reason="SHIELD_PURCHASE",
            reference_type="USER_SHIELD",
            reference_id=owned.id,
        )
        await session.flush()
        owned.shield = shield
        return ShieldPurchase(shield=shield, active_until=owned.active_until)

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
        if selected is None or selected.active_until is None:
            raise ShieldNotFound
        raise ShieldNotPurchasable

    async def apply_outgoing_attack_time_penalty(
        self, session: AsyncSession, user_id: int, duration: timedelta
    ) -> None:
        """An outgoing attack makes Mohammadi protection expire twice as fast."""
        now = datetime.now(UTC)
        result = await session.execute(
            select(UserShield)
            .join(Shield, UserShield.shield_id == Shield.id)
            .where(
                UserShield.user_id == user_id,
                UserShield.active_until > now,
                Shield.name == "سپر محمدی",
            )
            .with_for_update()
        )
        active = result.scalar_one_or_none()
        if active is not None:
            active.active_until -= duration

    async def consume_for_attack(
        self,
        session: AsyncSession,
        user_id: int,
        incoming_damage: int,
        *,
        teacher_names: tuple[str, ...] | None = None,
    ) -> ShieldMitigation:
        """Block an attack completely while a timed shield is active."""
        return await self.mitigate_attack(
            session,
            user_id,
            incoming_damage,
            for_update=True,
            teacher_names=teacher_names,
        )

    async def mitigate_attack(
        self,
        session: AsyncSession,
        user_id: int,
        incoming_damage: int,
        *,
        for_update: bool = False,
        teacher_names: tuple[str, ...] | None = None,
    ) -> ShieldMitigation:
        """Return complete protection when the user has an active timed shield."""
        if incoming_damage < 0:
            raise GameConfigurationError("Incoming damage cannot be negative")
        now = datetime.now(UTC)
        statement = (
            select(UserShield)
            .where(
                UserShield.user_id == user_id,
                UserShield.active_until.is_not(None),
                UserShield.active_until > now,
            )
            .options(selectinload(UserShield.shield))
            .order_by(UserShield.is_equipped.desc(), UserShield.id)
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        active = result.scalar_one_or_none()
        if active is None or self._kazemi_bypassed(active.shield, teacher_names or ()):
            return ShieldMitigation(incoming_damage, 0, incoming_damage)
        self.validate(active.shield)
        return ShieldMitigation(incoming_damage, incoming_damage, 0)


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
        if not 0 <= int(str(values.get("reduction_percent", -1))) <= 100:
            raise ValueError("reduction_percent must be between 0 and 100")
        if int(str(values.get("flat_absorption", -1))) < 0:
            raise ValueError("flat_absorption cannot be negative")
        if int(str(values.get("purchase_price", -1))) < 0:
            raise ValueError("purchase_price cannot be negative")
        if int(str(values.get("unlock_level", 0))) < 1:
            raise ValueError("unlock_level must be positive")
        if int(str(values.get("duration_minutes", 0))) < 1:
            raise ValueError("duration_minutes must be positive")
        daily_limit = values.get("daily_limit")
        if daily_limit is not None and int(str(daily_limit)) < 1:
            raise ValueError("daily_limit must be positive or unlimited")
        if values.get("purchase_resource") not in (
            ResourceType.COIN,
            ResourceType.DIAMOND,
        ):
            raise ValueError("purchase_resource must be coin or diamond")
        emoji_value = values.get("emoji")
        if emoji_value is not None and len(str(emoji_value)) > 32:
            raise ValueError("emoji must be at most 32 characters")

    async def create_shield(self, session: AsyncSession, **values: object) -> Shield:
        values.setdefault("reduction_percent", 0)
        values.setdefault("flat_absorption", 0)
        values.setdefault("purchase_resource", ResourceType.COIN)
        values.setdefault("daily_limit", None)
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
            "duration_minutes": values.get("duration_minutes", shield.duration_minutes),
            "daily_limit": values.get("daily_limit", shield.daily_limit),
            "purchase_resource": values.get(
                "purchase_resource", shield.purchase_resource
            ),
            "emoji": values.get("emoji", shield.emoji),
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
