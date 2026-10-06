from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType, TeacherStatus
from app.core.game_logic import GameConfig, GameConfigurationError, game_config
from app.models.recovery import Recovery
from app.models.user_teacher import UserTeacher
from app.repositories.teacher import TeacherRepository
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    HospitalFull,
    HospitalUpgradeUnavailable,
    InsufficientDiamonds,
    InvalidTeacherState,
    OperationNotConfigured,
    ResourceNotFound,
    SchoolUserNotFound,
    TeacherNotOwned,
)


@dataclass(frozen=True)
class HospitalSnapshot:
    level: int
    capacity: int
    occupied: int
    recovery_minutes: int
    next_capacity: int | None
    next_recovery_minutes: int | None
    upgrade_cost: int | None
    required_player_level: int | None
    player_level: int


class HospitalService:
    def __init__(
        self,
        repository: TeacherRepository | None = None,
        *,
        config: GameConfig | None = None,
    ) -> None:
        self.repository = repository or TeacherRepository()
        self.config = config or game_config

    def can_activate(self) -> bool:
        return self.config.instant_recovery_diamond_cost is not None

    def can_begin_recovery(self) -> bool:
        return self.config.recovery_is_configured

    def instant_recovery_cost(self) -> int | None:
        return self.config.instant_recovery_diamond_cost

    @staticmethod
    async def _occupied(session: AsyncSession, user_id: int) -> int:
        return int(
            await session.scalar(
                select(func.count(Recovery.id))
                .join(UserTeacher, Recovery.user_teacher_id == UserTeacher.id)
                .where(UserTeacher.user_id == user_id, Recovery.completed_at.is_(None))
            )
            or 0
        )

    async def snapshot(self, session: AsyncSession, user_id: int) -> HospitalSnapshot:
        user = await self.repository.get_user(session, user_id)
        if user is None:
            raise SchoolUserNotFound
        level = user.hospital_level
        current = self.config.hospital_level(level)
        next_level = self.config.hospital_levels.get(level + 1)
        return HospitalSnapshot(
            level=level,
            capacity=current.capacity,
            occupied=await self._occupied(session, user_id),
            recovery_minutes=current.recovery_minutes,
            next_capacity=next_level.capacity if next_level else None,
            next_recovery_minutes=(
                next_level.recovery_minutes if next_level is not None else None
            ),
            upgrade_cost=next_level.diamond_cost if next_level else None,
            required_player_level=next_level.required_player_level
            if next_level
            else None,
            player_level=user.level,
        )

    async def upgrade(self, session: AsyncSession, user_id: int) -> int:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise SchoolUserNotFound
        next_level = self.config.hospital_levels.get(user.hospital_level + 1)
        if (
            next_level is None
            or next_level.diamond_cost is None
            or user.level < next_level.required_player_level
        ):
            raise HospitalUpgradeUnavailable
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        if resources.diamond < next_level.diamond_cost:
            raise InsufficientDiamonds
        await ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=next_level.diamond_cost,
            reason="HOSPITAL_UPGRADE",
            reference_type="USER",
            reference_id=user_id,
        )
        await ResourceService.credit_banana(
            session,
            resources,
            user_id=user_id,
            amount=self.config.upgrade_banana_reward(next_level.diamond_cost),
            reason="HOSPITAL_UPGRADE_XP",
            reference_type="USER",
            reference_id=user_id,
        )
        user.hospital_level += 1
        await session.flush()
        return user.hospital_level

    @staticmethod
    def ready_for_discharge(
        teacher: UserTeacher, *, now: datetime | None = None
    ) -> bool:
        if teacher.status is not TeacherStatus.RECOVERING:
            return False
        now = now or datetime.now(UTC)
        for recovery in teacher.recoveries:
            if recovery.completed_at is None:
                end_at = recovery.recovery_end_at
                if end_at.tzinfo is None:
                    end_at = end_at.replace(tzinfo=UTC)
                return end_at <= now
        return False

    async def discharge(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        await self.repository.get_user_for_update(session, user_id)
        teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.current_hp <= 0:
            await session.delete(teacher)
            await session.flush()
            raise InvalidTeacherState
        if not self.ready_for_discharge(teacher):
            raise InvalidTeacherState
        now = datetime.now(UTC)
        for recovery in teacher.recoveries:
            if recovery.completed_at is None:
                recovery.completed_at = now
        teacher.current_hp = teacher.teacher.max_hp
        teacher.status = TeacherStatus.ACTIVE
        await session.flush()
        return teacher

    async def instant_recover(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        await self.repository.get_user_for_update(session, user_id)
        resources = await self.repository.get_resources_for_update(session, user_id)
        teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.current_hp <= 0:
            await session.delete(teacher)
            await session.flush()
            raise InvalidTeacherState
        if teacher.status not in {TeacherStatus.INJURED, TeacherStatus.RECOVERING}:
            raise InvalidTeacherState
        if self.ready_for_discharge(teacher):
            raise InvalidTeacherState
        cost = self.config.instant_recovery_diamond_cost
        if cost is None:
            raise OperationNotConfigured
        await ResourceService.debit(
            session,
            resources,
            user_id=user_id,
            resource_type=ResourceType.DIAMOND,
            amount=cost,
            reason="TEACHER_INSTANT_RECOVERY",
            reference_type="USER_TEACHER",
            reference_id=teacher.id,
        )
        now = datetime.now(UTC)
        for recovery in teacher.recoveries:
            if recovery.completed_at is None:
                recovery.completed_at = now
        teacher.current_hp = teacher.teacher.max_hp
        teacher.status = TeacherStatus.ACTIVE
        await session.flush()
        return teacher

    async def patients(self, session: AsyncSession, user_id: int) -> list[UserTeacher]:
        teachers = await self.repository.list_owned(session, user_id)
        changed = False
        living_teachers: list[UserTeacher] = []
        for teacher in teachers:
            # Zero HP is permanent death. Clean up legacy zero-HP rows instead
            # of exposing a path that can resurrect them.
            if teacher.current_hp <= 0:
                await session.delete(teacher)
                changed = True
                continue
            living_teachers.append(teacher)
        if changed:
            await session.flush()
        return [
            teacher
            for teacher in living_teachers
            if teacher.status
            in {
                TeacherStatus.INJURED,
                TeacherStatus.DISABLED,
                TeacherStatus.RECOVERING,
            }
            or (
                teacher.status is TeacherStatus.ACTIVE
                and teacher.current_hp < teacher.teacher.max_hp
            )
        ]

    async def begin_recovery(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        user = await self.repository.get_user_for_update(session, user_id)
        if user is None:
            raise SchoolUserNotFound
        teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.current_hp <= 0:
            await session.delete(teacher)
            await session.flush()
            raise InvalidTeacherState
        if teacher.status not in {TeacherStatus.INJURED, TeacherStatus.ACTIVE}:
            raise InvalidTeacherState
        if (
            teacher.status is TeacherStatus.ACTIVE
            and teacher.current_hp >= teacher.teacher.max_hp
        ):
            raise InvalidTeacherState
        if any(recovery.completed_at is None for recovery in teacher.recoveries):
            raise InvalidTeacherState
        if (
            await self._occupied(session, user_id)
            >= self.config.hospital_level(user.hospital_level).capacity
        ):
            raise HospitalFull
        try:
            duration_minutes = self.config.hospital_recovery_minutes(
                user.hospital_level
            )
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc

        started_at = datetime.now(UTC)
        recovery = Recovery(
            user_teacher_id=teacher.id,
            recovery_started_at=started_at,
            recovery_end_at=started_at + timedelta(minutes=duration_minutes),
        )
        session.add(recovery)
        teacher.status = TeacherStatus.RECOVERING
        await session.flush()
        return teacher

    async def send_to_hospital(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        """Manually send a damaged, still-usable teacher to recovery."""
        return await self.begin_recovery(session, user_id, user_teacher_id)
