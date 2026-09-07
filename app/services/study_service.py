from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.study_pack import StudyPack
from app.models.study_session import StudySession
from app.services.reward_service import RewardService, RewardSpec


class StudyError(RuntimeError):
    pass


class StudyAlreadyActive(StudyError):
    def __init__(self, study: StudySession) -> None:
        self.study = study
        super().__init__("another study pack is active")


class StudyPackNotFound(StudyError):
    pass


@dataclass(frozen=True)
class StudyStartResult:
    study: StudySession
    completed_reward: tuple[ResourceType, int] | None = None


class StudyService:
    def __init__(self, reward_service: RewardService | None = None) -> None:
        self.reward_service = reward_service or RewardService()
    async def packs(self, session: AsyncSession) -> list[StudyPack]:
        result = await session.execute(
            select(StudyPack)
            .where(StudyPack.is_active.is_(True))
            .order_by(StudyPack.duration_minutes, StudyPack.id)
        )
        return list(result.scalars().all())

    async def get_pack(
        self, session: AsyncSession, pack_key: str, *, active_only: bool = True
    ) -> StudyPack | None:
        statement = select(StudyPack).where(StudyPack.key == pack_key)
        if active_only:
            statement = statement.where(StudyPack.is_active.is_(True))
        return await session.scalar(statement)

    async def active(self, session: AsyncSession, user_id: int) -> StudySession | None:
        result = await session.execute(
            select(StudySession)
            .where(StudySession.user_id == user_id, StudySession.completed_at.is_(None))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def start(self, session: AsyncSession, user_id: int, pack_key: str, *, now: datetime | None = None) -> StudyStartResult:
        pack = await self.get_pack(session, pack_key)
        if pack is None:
            raise StudyPackNotFound
        now = now or datetime.now(UTC)
        active = await self.active(session, user_id)
        completed_reward = None
        if active is not None:
            if active.ends_at > now:
                raise StudyAlreadyActive(active)
            completed_reward = await self._complete(session, active, now)

        study = StudySession(
            user_id=user_id,
            pack_key=pack_key,
            started_at=now,
            ends_at=now + timedelta(minutes=pack.duration_minutes),
        )
        session.add(study)
        await session.flush()
        return StudyStartResult(study=study, completed_reward=completed_reward)

    async def settle(self, session: AsyncSession, user_id: int, *, now: datetime | None = None) -> tuple[StudySession | None, tuple[ResourceType, int] | None]:
        now = now or datetime.now(UTC)
        active = await self.active(session, user_id)
        if active is None or active.ends_at > now:
            return active, None
        reward = await self._complete(session, active, now)
        return active, reward

    async def _complete(self, session: AsyncSession, study: StudySession, now: datetime) -> tuple[ResourceType, int]:
        pack = await self.get_pack(session, study.pack_key, active_only=False)
        if pack is None:
            raise StudyPackNotFound
        result = await self.reward_service.grant(
            session,
            user_id=study.user_id,
            spec=RewardSpec(ResourceType(pack.reward_resource), pack.reward_amount),
            source="STUDY",
            reference_type="STUDY_SESSION",
            reference_id=study.id,
        )
        study.completed_at = now
        await session.flush()
        return ResourceType(pack.reward_resource), result.reward.amount if result else pack.reward_amount
