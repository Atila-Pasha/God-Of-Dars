from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType, TeacherStatus
from app.core.game_logic import GameConfig, GameConfigurationError, game_config
from app.models.teacher import Teacher
from app.models.user_teacher import UserTeacher
from app.repositories.teacher import TeacherRepository
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    InsufficientCoins,
    InvalidTeacherState,
    OperationNotConfigured,
    ResourceNotFound,
    TeacherAlreadyOwned,
    TeacherLimitReached,
    TeacherLocked,
    TeacherNotFound,
    TeacherNotOwned,
    TeacherNotPurchasable,
    TeacherSlotLocked,
)


@dataclass(frozen=True)
class TeacherCapacity:
    owned: int
    available: int
    maximum: int


@dataclass(frozen=True)
class TeacherAttackSnapshot:
    user_teacher_id: int
    teacher_id: int
    damage: int
    status: TeacherStatus


class TeacherService:
    def __init__(
        self,
        repository: TeacherRepository | None = None,
        *,
        config: GameConfig | None = None,
    ) -> None:
        self.repository = repository or TeacherRepository()
        self.config = config or game_config

    async def capacity(self, session: AsyncSession, user_id: int) -> TeacherCapacity:
        user = await self.repository.get_user(session, user_id)
        if user is None:
            raise TeacherNotFound
        owned = await self.repository.count_owned(session, user_id)
        return TeacherCapacity(
            owned=owned,
            available=self.config.teacher_slots(user.level),
            maximum=self.config.ownership_limit,
        )

    async def owned(self, session: AsyncSession, user_id: int) -> list[UserTeacher]:
        return await self.repository.list_owned(session, user_id)

    async def get_owned(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        """Return one teacher owned by the user for the detail view."""
        owned_teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if owned_teacher is None:
            raise TeacherNotOwned
        return owned_teacher

    async def catalog(self, session: AsyncSession, user_id: int) -> list[Teacher]:
        return await self.repository.list_catalog(session, user_id)

    async def catalog_teacher(self, session: AsyncSession, teacher_id: int) -> Teacher:
        teacher = await self.repository.get_catalog_teacher(session, teacher_id)
        if teacher is None:
            raise TeacherNotFound
        return teacher

    def sell_price(self, owned_teacher: UserTeacher) -> int:
        try:
            return self.config.teacher_sell_price(
                owned_teacher.teacher.id,
                owned_teacher.teacher.purchase_price,
            )
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc

    async def buy(
        self, session: AsyncSession, user_id: int, teacher_id: int
    ) -> UserTeacher:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise TeacherNotFound
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        teacher = await self.repository.get_catalog_teacher(session, teacher_id)
        if teacher is None:
            raise TeacherNotFound
        if teacher.is_active is False:
            raise TeacherNotPurchasable
        if await self.repository.get_owned_by_teacher_for_update(
            session, user_id, teacher_id
        ):
            raise TeacherAlreadyOwned

        owned_count = await self.repository.count_owned(session, user_id)
        level_capacity = self.config.teacher_slots(user.level)
        if owned_count >= level_capacity:
            raise TeacherSlotLocked
        if (
            self.config.ownership_limit is not None
            and owned_count >= self.config.ownership_limit
        ):
            raise TeacherLimitReached
        available_slots = self.config.teacher_slots(user.level)
        if owned_count >= available_slots:
            raise TeacherSlotLocked
        if user.level < teacher.unlock_level:
            raise TeacherLocked
        if teacher.purchase_price < 0:
            raise TeacherNotPurchasable
        if resources.coin < teacher.purchase_price:
            raise InsufficientCoins

        owned_teacher = UserTeacher(
            user_id=user_id,
            teacher_id=teacher.id,
            level=1,
            current_hp=teacher.max_hp,
            status=TeacherStatus.ACTIVE,
        )
        session.add(owned_teacher)
        await session.flush()
        ResourceService.debit_coin(
            session,
            resources,
            user_id=user_id,
            amount=teacher.purchase_price,
            reason="TEACHER_PURCHASE",
            reference_type="USER_TEACHER",
            reference_id=owned_teacher.id,
        )
        await session.flush()
        owned_teacher.teacher = teacher
        return owned_teacher

    async def upgrade(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise TeacherNotOwned
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        owned_teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if owned_teacher is None:
            raise TeacherNotOwned
        if owned_teacher.status is not TeacherStatus.ACTIVE:
            raise InvalidTeacherState

        next_level = owned_teacher.level + 1
        current_damage = self.damage(owned_teacher)
        try:
            next_damage = self.config.teacher_damage(
                owned_teacher.teacher.id,
                next_level,
                owned_teacher.teacher.damage,
            )
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc
        if next_damage <= current_damage:
            raise OperationNotConfigured
        if owned_teacher.teacher.upgrade_price < 0:
            raise OperationNotConfigured
        if resources.diamond < owned_teacher.teacher.upgrade_price:
            raise InsufficientCoins

        ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=owned_teacher.teacher.upgrade_price,
            reason="TEACHER_UPGRADE",
            reference_type="USER_TEACHER",
            reference_id=owned_teacher.id,
        )
        ResourceService.credit_banana(
            session,
            resources,
            user_id=user_id,
            amount=self.config.upgrade_banana_reward(owned_teacher.teacher.upgrade_price),
            reason="TEACHER_UPGRADE_XP",
            reference_type="USER_TEACHER",
            reference_id=owned_teacher.id,
        )
        owned_teacher.level = next_level
        await session.flush()
        return owned_teacher

    async def sell(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> int:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise TeacherNotOwned
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        owned_teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if owned_teacher is None:
            raise TeacherNotOwned
        try:
            sell_price = self.config.teacher_sell_price(
                owned_teacher.teacher.id,
                owned_teacher.teacher.purchase_price,
            )
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc

        await session.delete(owned_teacher)
        ResourceService.credit_coin(
            session,
            resources,
            user_id=user_id,
            amount=sell_price,
            reason="TEACHER_SELL",
            reference_type="USER_TEACHER",
            reference_id=user_teacher_id,
        )
        await session.flush()
        return sell_price

    async def activate(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise TeacherNotOwned
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        owned_teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if owned_teacher is None:
            raise TeacherNotOwned
        if owned_teacher.status is not TeacherStatus.DISABLED:
            raise InvalidTeacherState
        cost = self.config.instant_recovery_diamond_cost
        if cost is None:
            raise OperationNotConfigured

        ResourceService.debit(
            session,
            resources,
            user_id=user_id,
            resource_type=ResourceType.DIAMOND,
            amount=cost,
            reason="TEACHER_ACTIVATION",
            reference_type="USER_TEACHER",
            reference_id=owned_teacher.id,
        )
        owned_teacher.status = TeacherStatus.ACTIVE
        owned_teacher.current_hp = owned_teacher.teacher.max_hp
        await session.flush()
        return owned_teacher

    def damage(self, owned_teacher: UserTeacher) -> int:
        if owned_teacher.level == 1:
            return owned_teacher.teacher.damage
        try:
            return self.config.teacher_damage(
                owned_teacher.teacher.id,
                owned_teacher.level,
                owned_teacher.teacher.damage,
            )
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc

    def can_upgrade(self, owned_teacher: UserTeacher) -> bool:
        if owned_teacher.status is not TeacherStatus.ACTIVE:
            return False
        try:
            next_damage = self.config.teacher_damage(
                owned_teacher.teacher.id,
                owned_teacher.level + 1,
                owned_teacher.teacher.damage,
            )
            return next_damage > self.damage(owned_teacher)
        except (GameConfigurationError, OperationNotConfigured):
            return False

    def can_sell(self, owned_teacher: UserTeacher) -> bool:
        try:
            self.sell_price(owned_teacher)
        except OperationNotConfigured:
            return False
        return True

    async def attack_snapshot(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> TeacherAttackSnapshot:
        owned_teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if owned_teacher is None:
            raise TeacherNotOwned
        if owned_teacher.status is not TeacherStatus.ACTIVE:
            raise InvalidTeacherState
        return TeacherAttackSnapshot(
            user_teacher_id=owned_teacher.id,
            teacher_id=owned_teacher.teacher.id,
            damage=self.damage(owned_teacher),
            status=owned_teacher.status,
        )
