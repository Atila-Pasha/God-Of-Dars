from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.enums import AttackStatus, ResourceType
from app.db.session import AsyncSessionLocal
from app.models.archer import Archer, ArrowPack, UserArcher, UserArrow
from app.models.attack import Attack
from app.models.notification import Notification
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.workers.attack_resolver import resolve_due_archer_shots


@pytest.mark.asyncio
@pytest.mark.parametrize("sticker_id", ["fake-sticker", None])
async def test_midway_shot_spends_one_arrow_and_queues_sticker_before_text(
    sticker_id: str | None,
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
        assert await resolve_due_archer_shots() >= 1
        assert await resolve_due_archer_shots() == 0
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
