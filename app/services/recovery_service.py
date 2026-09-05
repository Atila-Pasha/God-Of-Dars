from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType, TeacherStatus
from app.core.game_logic import GameConfig, GameConfigurationError, game_config
from app.models.recovery import Recovery
from app.models.user_teacher import UserTeacher
from app.repositories.teacher import TeacherRepository
from app.services.castle_service import CastleService
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    InvalidTeacherState,
    OperationNotConfigured,
    TeacherNotOwned,
)


class HospitalService:
    def __init__(
        self,
        repository: TeacherRepository | None = None,
        castle_service: CastleService | None = None,
        *,
        config: GameConfig | None = None,
    ) -> None:
        self.repository = repository or TeacherRepository()
        self.castle_service = castle_service or CastleService()
        self.config = config or game_config

    def can_activate(self) -> bool:
        return self.config.instant_recovery_diamond_cost is not None

    def can_begin_recovery(self) -> bool:
        return self.config.recovery_is_configured

    def instant_recovery_cost(self) -> int | None:
        return self.config.instant_recovery_diamond_cost

    async def instant_recover(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.status not in {TeacherStatus.INJURED, TeacherStatus.RECOVERING}:
            raise InvalidTeacherState
        cost = self.config.instant_recovery_diamond_cost
        if cost is None:
            raise OperationNotConfigured
        resources = await self.repository.get_resources_for_update(session, user_id)
        ResourceService.debit(
            session, resources, user_id=user_id, resource_type=ResourceType.DIAMOND,
            amount=cost, reason="TEACHER_INSTANT_RECOVERY",
            reference_type="USER_TEACHER", reference_id=teacher.id,
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
        now = datetime.now(UTC)
        changed = False
        for teacher in teachers:
            # Repair legacy rows created before zero HP was automatically
            # marked as disabled, so they appear in the hospital immediately.
            if teacher.current_hp <= 0 and teacher.status is TeacherStatus.ACTIVE:
                teacher.current_hp = 0
                teacher.status = TeacherStatus.DISABLED
                changed = True
            active_recovery = next(
                (
                    recovery
                    for recovery in teacher.recoveries
                    if recovery.completed_at is None
                ),
                None,
            )
            if (
                teacher.status is TeacherStatus.RECOVERING
                and active_recovery is not None
                and active_recovery.recovery_end_at <= now
            ):
                active_recovery.completed_at = now
                teacher.current_hp = teacher.teacher.max_hp
                teacher.status = TeacherStatus.ACTIVE
                changed = True
        if changed:
            await session.flush()
        return [
            teacher
            for teacher in teachers
            if teacher.status
            in {
                TeacherStatus.INJURED,
                TeacherStatus.DISABLED,
                TeacherStatus.RECOVERING,
            }
        ]

    async def begin_recovery(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> UserTeacher:
        teacher = await self.repository.get_owned_for_update(
            session, user_id, user_teacher_id
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.status not in {TeacherStatus.INJURED, TeacherStatus.ACTIVE}:
            raise InvalidTeacherState
        if (
            teacher.status is TeacherStatus.ACTIVE
            and teacher.current_hp >= teacher.teacher.max_hp
        ):
            raise InvalidTeacherState
        if any(recovery.completed_at is None for recovery in teacher.recoveries):
            raise InvalidTeacherState
        try:
            duration_minutes = self.config.recovery_minutes(
                (await self.castle_service.snapshot(session, user_id)).strength
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
