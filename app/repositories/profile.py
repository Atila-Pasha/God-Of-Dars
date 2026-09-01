from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AttackStatus, TeacherStatus
from app.models.answer import Answer
from app.models.attack import Attack
from app.models.castle import Castle
from app.models.user import User
from app.models.user_teacher import UserTeacher


@dataclass(frozen=True)
class ProfileSnapshot:
    user: User
    teachers_count: int
    active_teachers_count: int
    attacks_sent: int
    successful_attacks: int
    pending_attacks: int
    attacks_received: int
    damage_dealt: int
    loot_coin: int
    loot_diamond: int
    loot_banana: int
    answers_count: int
    correct_answers: int
    referrals_count: int


class ProfileRepository:
    async def get_snapshot(
        self, session: AsyncSession, user_id: int
    ) -> ProfileSnapshot | None:
        user_result = await session.execute(
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.resources),
                selectinload(User.castle).selectinload(Castle.defense),
            )
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            return None

        attack_result = await session.execute(
            select(
                func.count(Attack.id)
                .filter(Attack.attacker_id == user_id)
                .label("attacks_sent"),
                func.count(Attack.id)
                .filter(
                    Attack.attacker_id == user_id,
                    Attack.is_successful.is_(True),
                )
                .label("successful_attacks"),
                func.count(Attack.id)
                .filter(
                    Attack.attacker_id == user_id,
                    Attack.status == AttackStatus.PENDING,
                )
                .label("pending_attacks"),
                func.count(Attack.id)
                .filter(Attack.target_id == user_id)
                .label("attacks_received"),
                func.coalesce(
                    func.sum(Attack.result_damage).filter(
                        Attack.attacker_id == user_id
                    ),
                    0,
                ).label("damage_dealt"),
                func.coalesce(
                    func.sum(Attack.loot_coin).filter(
                        Attack.attacker_id == user_id
                    ),
                    0,
                ).label("loot_coin"),
                func.coalesce(
                    func.sum(Attack.loot_diamond).filter(
                        Attack.attacker_id == user_id
                    ),
                    0,
                ).label("loot_diamond"),
                func.coalesce(
                    func.sum(Attack.loot_banana).filter(
                        Attack.attacker_id == user_id
                    ),
                    0,
                ).label("loot_banana"),
            )
        )
        attacks = attack_result.one()

        answer_result = await session.execute(
            select(
                func.count(Answer.id).label("answers_count"),
                func.count(Answer.id)
                .filter(Answer.is_correct.is_(True))
                .label("correct_answers"),
            ).where(Answer.user_id == user_id)
        )
        answers = answer_result.one()

        teacher_result = await session.execute(
            select(
                func.count(UserTeacher.id).label("teachers_count"),
                func.count(UserTeacher.id)
                .filter(UserTeacher.status == TeacherStatus.ACTIVE)
                .label("active_teachers_count"),
            ).where(UserTeacher.user_id == user_id)
        )
        teachers = teacher_result.one()

        referral_count = await session.scalar(
            select(func.count(User.id)).where(User.referrer_id == user_id)
        )

        return ProfileSnapshot(
            user=user,
            teachers_count=int(teachers.teachers_count),
            active_teachers_count=int(teachers.active_teachers_count),
            attacks_sent=int(attacks.attacks_sent),
            successful_attacks=int(attacks.successful_attacks),
            pending_attacks=int(attacks.pending_attacks),
            attacks_received=int(attacks.attacks_received),
            damage_dealt=int(attacks.damage_dealt),
            loot_coin=int(attacks.loot_coin),
            loot_diamond=int(attacks.loot_diamond),
            loot_banana=int(attacks.loot_banana),
            answers_count=int(answers.answers_count),
            correct_answers=int(answers.correct_answers),
            referrals_count=int(referral_count or 0),
        )
