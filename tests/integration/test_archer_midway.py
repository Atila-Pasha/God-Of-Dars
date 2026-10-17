from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.enums import AttackStatus, ResourceType
from app.db.session import AsyncSessionLocal
from app.models.archer import Archer, ArrowPack, UserArcher, UserArrow
from app.models.attack import Attack
from app.models.knight import Knight, UserKnight
from app.models.notification import Notification
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.workers.attack_resolver import resolve_due_archer_shots


@pytest.mark.asyncio
@pytest.mark.parametrize("sticker_id", ["fake-sticker", None])
@pytest.mark.parametrize("in_group", [False, True])
@pytest.mark.parametrize("launch_message_id", [777, None])
async def test_midway_shot_spends_one_arrow_and_queues_sticker_before_text(
    sticker_id: str | None,
    in_group: bool,
    launch_message_id: int | None,
) -> None:
    token = uuid4().hex[:10]
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        attacker = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000), first_name="mid-attacker"
        )
        defender = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000), first_name="mid-defender"
        )
        teacher = Teacher(
            name=f"mid-teacher-{token}",
            damage=10,
            max_hp=30,
            purchase_price=1,
            upgrade_price=1,
        )
        archer = Archer(
            name=f"mid-archer-{token}",
            power=4,
            purchase_price=1,
            purchase_resource=ResourceType.COIN,
            upgrade_price=1,
            unlock_level=1,
            sticker=sticker_id,
        )
        pack = ArrowPack(
            name=f"mid-pack-{token}",
            power=2,
            quantity=2,
            purchase_price=1,
            purchase_resource=ResourceType.COIN,
            unlock_level=1,
        )
        session.add_all((attacker, defender, teacher, archer, pack))
        await session.flush()
        owned_teacher = UserTeacher(
            user_id=attacker.id, teacher_id=teacher.id, current_hp=30
        )
        session.add_all(
            (
                owned_teacher,
                UserArcher(user_id=defender.id, archer_id=archer.id, level=1),
                UserArrow(
                    user_id=defender.id, pack_id=pack.id, quantity=2, is_equipped=True
                ),
            )
        )
        await session.flush()
        attack = Attack(
            attacker_id=attacker.id,
            target_id=defender.id,
            teacher_id=owned_teacher.id,
            status=AttackStatus.PENDING,
            created_at=now - timedelta(seconds=61),
            resolve_at=now + timedelta(seconds=59),
            attack_command_id=str(uuid4()),
            source_chat_id=-100987654321 if in_group else None,
            launch_chat_id=(-100987654321 if in_group else attacker.telegram_user_id),
            launch_message_id=launch_message_id,
            teacher_name_snapshot=teacher.name,
            teacher_damage_snapshot=10,
            target_castle_strength_snapshot=100,
            target_defense_power_snapshot=5,
        )
        session.add(attack)
        await session.flush()
        attack_id, attacker_id, defender_id = attack.id, attacker.id, defender.id
        teacher_id, archer_id, pack_id = teacher.id, archer.id, pack.id

    try:
        assert await resolve_due_archer_shots(only_attack_id=attack_id) == 1
        assert await resolve_due_archer_shots(only_attack_id=attack_id) == 0
        async with AsyncSessionLocal() as session:
            shot = await session.get(Attack, attack_id)
            owned_teacher = await session.scalar(
                select(UserTeacher).where(UserTeacher.user_id == attacker_id)
            )
            stock = await session.scalar(
                select(UserArrow).where(UserArrow.user_id == defender_id)
            )
            notifications = list(
                await session.scalars(
                    select(Notification).where(
                        Notification.idempotency_key.in_(
                            (
                                f"ARCHER_MID_STICKER:{attack_id}",
                                f"ARCHER_MID_DAMAGE:{attack_id}",
                            )
                        )
                    )
                )
            )
            assert shot.archer_processed_at is not None
            assert shot.result_archer_injury == 6
            assert owned_teacher.current_hp == 24
            assert stock.quantity == 1
            assert len(notifications) == (2 if sticker_id else 1)
            expected_chat_id = -100987654321 if in_group else attacker.telegram_user_id
            assert all(
                row.payload["chat_id"] == expected_chat_id for row in notifications
            )
            assert all(
                row.payload.get("reply_to_message_id") == launch_message_id
                for row in notifications
            )
            damage = next(
                row
                for row in notifications
                if row.notification_type == "ARCHER_MID_DAMAGE"
            )
            if sticker_id:
                sticker = next(
                    row
                    for row in notifications
                    if row.notification_type == "ARCHER_MID_STICKER"
                )
                assert damage.payload["depends_on_key"] == sticker.idempotency_key
            else:
                assert "depends_on_key" not in damage.payload
            assert "6 HP" in damage.payload["text"]
            if in_group:
                assert "tg://emoji?id=" in damage.payload["text"]
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Notification).where(
                    Notification.idempotency_key.in_(
                        (
                            f"ARCHER_MID_STICKER:{attack_id}",
                            f"ARCHER_MID_DAMAGE:{attack_id}",
                        )
                    )
                )
            )
            await session.execute(delete(Attack).where(Attack.id == attack_id))
            await session.execute(
                delete(UserArrow).where(UserArrow.user_id == defender_id)
            )
            await session.execute(
                delete(UserArcher).where(UserArcher.user_id == defender_id)
            )
            await session.execute(
                delete(UserTeacher).where(UserTeacher.user_id == attacker_id)
            )
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))
            await session.execute(delete(Archer).where(Archer.id == archer_id))
            await session.execute(delete(ArrowPack).where(ArrowPack.id == pack_id))
            await session.execute(
                delete(User).where(User.id.in_((attacker_id, defender_id)))
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("guard_kind", ["archer", "knight"])
async def test_guard_hits_each_teacher_in_an_attack_team(guard_kind: str) -> None:
    token = uuid4().hex[:10]
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        attacker = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="team-attacker",
        )
        defender = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="team-defender",
        )
        teachers = [
            Teacher(
                name=f"team-{token}-{index}",
                damage=20,
                max_hp=80,
                purchase_price=1,
                upgrade_price=1,
            )
            for index in range(2)
        ]
        guard = (
            Archer(
                name=f"team-archer-{token}",
                power=4,
                purchase_price=1,
                upgrade_price=1,
            )
            if guard_kind == "archer"
            else Knight(
                name=f"team-knight-{token}",
                power=8,
                max_hp=20,
                purchase_price=1,
                upgrade_price=1,
            )
        )
        pack = (
            ArrowPack(
                name=f"team-pack-{token}",
                power=2,
                quantity=2,
                purchase_price=1,
            )
            if guard_kind == "archer"
            else None
        )
        session.add_all([attacker, defender, *teachers, guard])
        if pack is not None:
            session.add(pack)
        await session.flush()
        owned_teachers = [
            UserTeacher(user_id=attacker.id, teacher_id=row.id, current_hp=80)
            for row in teachers
        ]
        session.add_all(owned_teachers)
        if guard_kind == "archer":
            session.add_all(
                [
                    UserArcher(user_id=defender.id, archer_id=guard.id),
                    UserArrow(
                        user_id=defender.id,
                        pack_id=pack.id,
                        quantity=2,
                        is_equipped=True,
                    ),
                ]
            )
        else:
            session.add(
                UserKnight(
                    user_id=defender.id,
                    knight_id=guard.id,
                    current_hp=20,
                    is_equipped=True,
                )
            )
        await session.flush()
        command_id = str(uuid4())
        attacks = [
            Attack(
                attacker_id=attacker.id,
                target_id=defender.id,
                teacher_id=owned.id,
                status=AttackStatus.PENDING,
                created_at=now - timedelta(seconds=61),
                resolve_at=now + timedelta(seconds=59),
                attack_command_id=command_id,
                teacher_name_snapshot=teacher.name,
                teacher_damage_snapshot=20,
                target_castle_strength_snapshot=100,
                target_defense_power_snapshot=0,
            )
            for teacher, owned in zip(teachers, owned_teachers, strict=True)
        ]
        session.add_all(attacks)
        await session.flush()
        attack_ids = [row.id for row in attacks]
        attacker_id, defender_id = attacker.id, defender.id
        teacher_ids = [row.id for row in teachers]
        guard_id = guard.id
        pack_id = pack.id if pack is not None else None

    try:
        for attack_id in attack_ids:
            assert await resolve_due_archer_shots(only_attack_id=attack_id) == 1
        async with AsyncSessionLocal() as session:
            rows = [await session.get(Attack, attack_id) for attack_id in attack_ids]
            assert all(row.archer_processed_at is not None for row in rows)
            assert [row.result_archer_injury for row in rows] == (
                [6, 6] if guard_kind == "archer" else [8, 8]
            )
            notifications = list(
                await session.scalars(
                    select(Notification).where(
                        Notification.idempotency_key.in_(
                            [
                                f"ARCHER_MID_DAMAGE:{attack_id}"
                                for attack_id in attack_ids
                            ]
                        )
                    )
                )
            )
            assert len(notifications) == 2
            assert all(
                row.payload["chat_id"] == attacker.telegram_user_id
                for row in notifications
            )
            if guard_kind == "archer":
                stock = await session.scalar(
                    select(UserArrow).where(UserArrow.user_id == defender_id)
                )
                assert stock.quantity == 0
            else:
                knight = await session.scalar(
                    select(UserKnight).where(UserKnight.user_id == defender_id)
                )
                assert knight.current_hp == 10
                assert all(row.guard_reduction_snapshot == 16 for row in rows)
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Notification).where(
                    Notification.recipient_user_id == attacker_id
                )
            )
            await session.execute(delete(Attack).where(Attack.id.in_(attack_ids)))
            await session.execute(
                delete(UserTeacher).where(UserTeacher.user_id == attacker_id)
            )
            await session.execute(
                delete(UserArrow).where(UserArrow.user_id == defender_id)
            )
            await session.execute(
                delete(UserArcher).where(UserArcher.user_id == defender_id)
            )
            await session.execute(
                delete(UserKnight).where(UserKnight.user_id == defender_id)
            )
            await session.execute(delete(Teacher).where(Teacher.id.in_(teacher_ids)))
            await session.execute(
                delete(User).where(User.id.in_((attacker_id, defender_id)))
            )
            if pack_id is not None:
                await session.execute(delete(ArrowPack).where(ArrowPack.id == pack_id))
                await session.execute(delete(Archer).where(Archer.id == guard_id))
            else:
                await session.execute(delete(Knight).where(Knight.id == guard_id))
