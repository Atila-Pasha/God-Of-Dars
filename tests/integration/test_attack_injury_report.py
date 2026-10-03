from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.bot.banners import attack_teacher_injury_banner
from app.core.enums import AttackStatus
from app.db.session import AsyncSessionLocal
from app.models.attack import Attack
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.services.attack_service import AttackResult
from app.workers.attack_resolver import _command_result


@pytest.mark.asyncio
async def test_destroyed_teacher_is_reported_after_database_deletion() -> None:
    async with AsyncSessionLocal() as session:
        await session.begin()
        try:
            attacker = User(
                telegram_user_id=int(uuid4().int % 2_000_000_000),
                first_name="attacker",
            )
            target = User(
                telegram_user_id=int(uuid4().int % 2_000_000_000),
                first_name="target",
            )
            teacher = Teacher(
                name=f"injury-{uuid4().hex[:8]}",
                damage=10,
                max_hp=100,
                purchase_price=1,
                upgrade_price=1,
            )
            owned = UserTeacher(user=attacker, teacher=teacher, current_hp=1)
            session.add_all((attacker, target, owned))
            await session.flush()
            attack = Attack(
                attacker_id=attacker.id,
                target_id=target.id,
                teacher_id=owned.id,
                status=AttackStatus.RESOLVED,
                resolve_at=datetime.now(UTC),
                result_teacher_injury=1,
                result_damage=0,
                loot_coin=0,
                loot_diamond=0,
                loot_banana=0,
                teacher_damage_snapshot=10,
                target_castle_strength_snapshot=100,
                target_defense_power_snapshot=50,
                teacher_name_snapshot=teacher.name,
            )
            session.add(attack)
            await session.flush()
            await session.delete(owned)
            await session.flush()

            result = AttackResult(
                attack=attack,
                attacker_telegram_id=attacker.telegram_user_id,
                attacker_name=attacker.first_name,
                target_name=target.first_name,
                target_telegram_id=target.telegram_user_id,
                teacher_name=teacher.name,
                ability_text=None,
                castle_damage=0,
                teacher_injury=1,
                castle_strength_after=100,
                loot_coin=0,
                loot_diamond=0,
                loot_banana=0,
            )
            summary = await _command_result(session, result)

            assert summary is not None
            assert summary.teacher_injuries[0].damage == 1
            assert summary.teacher_injuries[0].lost
            assert "دبیرت را در نبرد از دست دادی" in attack_teacher_injury_banner(
                summary
            )
        finally:
            await session.rollback()
