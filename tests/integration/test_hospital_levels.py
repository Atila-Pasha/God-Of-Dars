"""Hospital bed locking and upgrade behavior against PostgreSQL."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import TeacherStatus
from app.db.session import AsyncSessionLocal, engine
from app.models.recovery import Recovery
from app.models.resource import Resource
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.services.recovery_service import HospitalService
from app.services.school_errors import HospitalFull

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"), reason="requires PostgreSQL"
)


@pytest.mark.asyncio
async def test_hospital_upgrade_adds_a_bed_and_shortens_new_recovery() -> None:
    await engine.dispose()
    suffix = uuid4().hex[:12]
    async with AsyncSessionLocal() as session, session.begin():
        player = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="hospital-test",
            level=3,
        )
        player.resources = Resource(diamond=500)
        teachers = [
            Teacher(
                name=f"hospital-{suffix}-{index}",
                damage=10,
                max_hp=100,
                purchase_price=10,
                upgrade_price=10,
                unlock_level=1,
            )
            for index in range(2)
        ]
        session.add_all([player, *teachers])
        await session.flush()
        owned = [
            UserTeacher(
                user_id=player.id,
                teacher_id=teacher.id,
                level=1,
                current_hp=50,
                status=TeacherStatus.INJURED,
            )
            for teacher in teachers
        ]
        session.add_all(owned)
        await session.flush()
        user_id, teacher_ids = player.id, [item.id for item in owned]

    service = HospitalService()

    async def admit(teacher_id: int) -> str:
        async with AsyncSessionLocal() as session:
            try:
                async with session.begin():
                    await service.begin_recovery(session, user_id, teacher_id)
            except HospitalFull:
                return "full"
        return "admitted"

    assert sorted(await asyncio.gather(*(admit(item) for item in teacher_ids))) == [
        "admitted",
        "full",
    ]

    async with AsyncSessionLocal() as session, session.begin():
        before = await service.snapshot(session, user_id)
        assert (before.level, before.capacity, before.occupied) == (1, 1, 1)
        first = await session.scalar(
            select(Recovery).where(Recovery.completed_at.is_(None))
        )
        assert first is not None
        first_minutes = (
            first.recovery_end_at - first.recovery_started_at
        ).total_seconds() / 60
        await service.upgrade(session, user_id)
        after = await service.snapshot(session, user_id)
        assert (after.level, after.capacity, after.occupied) == (2, 2, 1)

    async with AsyncSessionLocal() as session, session.begin():
        other = next(item for item in teacher_ids if item != first.user_teacher_id)
        await service.begin_recovery(session, user_id, other)
        rows = list(
            (
                await session.scalars(
                    select(Recovery).where(Recovery.completed_at.is_(None))
                )
            ).all()
        )
        assert len(rows) == 2
        second = next(item for item in rows if item.user_teacher_id == other)
        second_minutes = (
            second.recovery_end_at - second.recovery_started_at
        ).total_seconds() / 60
        assert second_minutes < first_minutes
        assert first_minutes == 240
        assert second_minutes == 192
        # A finished but not discharged patient still occupies a bed.
        current_first = next(
            item for item in rows if item.user_teacher_id == first.user_teacher_id
        )
        current_first.recovery_started_at = datetime.now(UTC) - timedelta(minutes=241)
        current_first.recovery_end_at = datetime.now(UTC) - timedelta(seconds=1)

    async with AsyncSessionLocal() as session, session.begin():
        assert (await service.snapshot(session, user_id)).occupied == 2
        await service.discharge(session, user_id, first.user_teacher_id)
        assert (await service.snapshot(session, user_id)).occupied == 1

    await engine.dispose()
