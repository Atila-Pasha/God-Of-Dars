"""Hospital bed locking and upgrade behavior against PostgreSQL."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.enums import AttackStatus, TeacherStatus
from app.db.session import AsyncSessionLocal, engine
from app.models.attack import Attack
from app.models.castle import Castle
from app.models.defense import Defense
from app.models.recovery import Recovery
from app.models.resource import Resource
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.services.attack_service import AttackService
from app.services.recovery_service import HospitalService
from app.services.school_errors import AttackInProgress, HospitalFull

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
        assert before.heal_hp_per_hour == 60
        assert before.next_heal_hp_per_hour == 75
        assert (
            await session.scalar(select(Castle.id).where(Castle.user_id == user_id))
            is None
        )
        first = await session.scalar(
            select(Recovery).where(
                Recovery.completed_at.is_(None),
                Recovery.user_teacher_id.in_(teacher_ids),
            )
        )
        assert first is not None
        first_minutes = (
            first.recovery_end_at - first.recovery_started_at
        ).total_seconds() / 60
        await service.upgrade(session, user_id)
        after = await service.snapshot(session, user_id)
        assert (after.level, after.capacity, after.occupied) == (2, 2, 1)
        assert after.heal_hp_per_hour == 75

    async with AsyncSessionLocal() as session, session.begin():
        other = next(item for item in teacher_ids if item != first.user_teacher_id)
        await service.begin_recovery(session, user_id, other)
        rows = list(
            (
                await session.scalars(
                    select(Recovery).where(
                        Recovery.completed_at.is_(None),
                        Recovery.user_teacher_id.in_(teacher_ids),
                    )
                )
            ).all()
        )
        assert len(rows) == 2
        second = next(item for item in rows if item.user_teacher_id == other)
        second_minutes = (
            second.recovery_end_at - second.recovery_started_at
        ).total_seconds() / 60
        assert second_minutes < first_minutes
        assert first_minutes == 50
        assert second_minutes == 40
        # Finishing treatment releases the bed; discharge is still required
        # before the teacher can fight again.
        current_first = next(
            item for item in rows if item.user_teacher_id == first.user_teacher_id
        )
        current_first.recovery_started_at = datetime.now(UTC) - timedelta(minutes=241)
        current_first.recovery_end_at = datetime.now(UTC) - timedelta(seconds=1)

    async with AsyncSessionLocal() as session, session.begin():
        assert (await service.snapshot(session, user_id)).occupied == 1
        await service.discharge(session, user_id, first.user_teacher_id)
        assert (await service.snapshot(session, user_id)).occupied == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_bed_and_interrupted_recovery_do_not_block_new_treatment() -> (
    None
):
    await engine.dispose()
    suffix = uuid4().hex[:12]
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        player = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="hospital-interruption",
        )
        opponent = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="hospital-opponent",
        )
        player.resources = Resource()
        opponent.resources = Resource()
        catalog = [
            Teacher(
                name=f"hospital-interruption-{suffix}-{index}",
                damage=10,
                max_hp=100,
                purchase_price=10,
                upgrade_price=10,
            )
            for index in range(2)
        ]
        session.add_all([player, opponent, *catalog])
        await session.flush()
        first = UserTeacher(
            user_id=player.id,
            teacher_id=catalog[0].id,
            current_hp=50,
            status=TeacherStatus.RECOVERING,
        )
        second = UserTeacher(
            user_id=player.id,
            teacher_id=catalog[1].id,
            current_hp=50,
            status=TeacherStatus.INJURED,
        )
        session.add_all([first, second])
        await session.flush()
        session.add(
            Recovery(
                user_teacher_id=first.id,
                recovery_started_at=now - timedelta(minutes=5),
                recovery_end_at=now - timedelta(minutes=1),
            )
        )
        attack = Attack(
            attacker_id=player.id,
            target_id=opponent.id,
            teacher_id=second.id,
            status=AttackStatus.PENDING,
            resolve_at=now + timedelta(minutes=5),
            teacher_damage_snapshot=10,
            target_castle_strength_snapshot=100,
            target_defense_power_snapshot=0,
        )
        session.add(attack)
        await session.flush()
        user_ids = (player.id, opponent.id)
        owned_ids = (first.id, second.id)
        catalog_ids = (catalog[0].id, catalog[1].id)
        attack_id = attack.id

    service = HospitalService()
    try:
        async with AsyncSessionLocal() as session, session.begin():
            assert (await service.snapshot(session, user_ids[0])).occupied == 0
            with pytest.raises(AttackInProgress):
                await service.begin_recovery(session, user_ids[0], owned_ids[1])
            attack = await session.get(Attack, attack_id)
            attack.status = AttackStatus.RESOLVED
            attack.resolved_at = datetime.now(UTC)
            await service.begin_recovery(session, user_ids[0], owned_ids[1])
            assert (await service.snapshot(session, user_ids[0])).occupied == 1

        async with AsyncSessionLocal() as session, session.begin():
            # This is the broken state left by older delayed attacks.
            owned = await session.get(UserTeacher, owned_ids[1])
            owned.status = TeacherStatus.INJURED
            await session.flush()
            await service.begin_recovery(session, user_ids[0], owned_ids[1])
            assert (await service.snapshot(session, user_ids[0])).occupied == 1
            completed, active = (
                await session.execute(
                    select(
                        func.count(Recovery.id).filter(
                            Recovery.completed_at.is_not(None)
                        ),
                        func.count(Recovery.id).filter(Recovery.completed_at.is_(None)),
                    ).where(Recovery.user_teacher_id == owned_ids[1])
                )
            ).one()
            assert (completed, active) == (1, 1)
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Attack).where(Attack.id == attack_id))
            await session.execute(
                delete(Recovery).where(Recovery.user_teacher_id.in_(owned_ids))
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.execute(delete(Teacher).where(Teacher.id.in_(catalog_ids)))
        await engine.dispose()


@pytest.mark.asyncio
async def test_late_attack_injury_closes_interrupted_hospital_recovery() -> None:
    await engine.dispose()
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        attacker = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="late-attack-attacker",
        )
        target = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="late-attack-target",
        )
        attacker.resources = Resource()
        target.resources = Resource(coin=100)
        attacker.castle = Castle(strength=100, defense=Defense(defense_power=0))
        target.castle = Castle(strength=100, defense=Defense(defense_power=4))
        catalog = Teacher(
            name=f"hospital-late-attack-{uuid4().hex[:12]}",
            damage=10,
            max_hp=100,
            purchase_price=10,
            upgrade_price=10,
        )
        session.add_all([attacker, target, catalog])
        await session.flush()
        owned = UserTeacher(
            user_id=attacker.id,
            teacher_id=catalog.id,
            current_hp=50,
            status=TeacherStatus.RECOVERING,
        )
        session.add(owned)
        await session.flush()
        recovery = Recovery(
            user_teacher_id=owned.id,
            recovery_started_at=now - timedelta(minutes=1),
            recovery_end_at=now + timedelta(minutes=10),
        )
        attack = Attack(
            attacker_id=attacker.id,
            target_id=target.id,
            teacher_id=owned.id,
            status=AttackStatus.PENDING,
            resolve_at=now - timedelta(seconds=1),
            teacher_damage_snapshot=10,
            target_castle_strength_snapshot=100,
            target_defense_power_snapshot=4,
        )
        session.add_all([recovery, attack])
        await session.flush()
        attack_id, owned_id, recovery_id = attack.id, owned.id, recovery.id
        user_ids = (attacker.id, target.id)
        catalog_id = catalog.id

    try:
        async with AsyncSessionLocal() as session:
            result = await AttackService().resolve_pending_attack(session, attack_id)
            assert result is not None and result.teacher_injury > 0
            owned = await session.get(UserTeacher, owned_id)
            recovery = await session.get(Recovery, recovery_id)
            assert owned.status is TeacherStatus.INJURED
            assert recovery.completed_at is not None
            # Keep this test isolated from attack rewards and notifications.
            await session.rollback()
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Attack).where(Attack.id == attack_id))
            await session.execute(delete(Recovery).where(Recovery.id == recovery_id))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.execute(delete(Teacher).where(Teacher.id == catalog_id))
        await engine.dispose()
