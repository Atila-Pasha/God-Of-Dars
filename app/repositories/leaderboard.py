from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AttackStatus
from app.models.answer import Answer
from app.models.attack import Attack
from app.models.resource import Resource
from app.models.user import User


@dataclass(frozen=True)
class LeaderboardRecord:
    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    primary_value: int
    secondary_value: int


class LeaderboardRepository:
    async def commanders(
        self, session: AsyncSession, *, limit: int
    ) -> list[LeaderboardRecord]:
        xp = func.coalesce(Resource.banana, 0)
        rows = (
            await session.execute(
                select(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                    User.level,
                    xp,
                )
                .outerjoin(Resource, Resource.user_id == User.id)
                .where(User.is_active.is_(True))
                .order_by(
                    User.level.desc(),
                    xp.desc(),
                    User.created_at.asc(),
                    User.id.asc(),
                )
                .limit(limit)
            )
        ).all()
        return [self._record(row) for row in rows]

    async def students(
        self, session: AsyncSession, *, limit: int
    ) -> list[LeaderboardRecord]:
        correct_answers = func.count(Answer.id).filter(
            Answer.is_correct.is_(True), Answer.is_valid.is_(True)
        )
        total_answers = func.count(Answer.id)
        accuracy = correct_answers * 1.0 / func.nullif(total_answers, 0)
        rows = (
            await session.execute(
                select(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                    correct_answers,
                    total_answers,
                )
                .join(Answer, Answer.user_id == User.id)
                .where(User.is_active.is_(True))
                .group_by(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                )
                .having(correct_answers > 0)
                .order_by(
                    correct_answers.desc(),
                    accuracy.desc(),
                    total_answers.asc(),
                    User.id.asc(),
                )
                .limit(limit)
            )
        ).all()
        return [self._record(row) for row in rows]

    async def fighters(
        self, session: AsyncSession, *, limit: int
    ) -> list[LeaderboardRecord]:
        # A multi-teacher attack creates multiple Attack rows. All rows share
        # attack_command_id, so count the command once. Legacy rows without a
        # command id use their own database id as a stable fallback.
        command_key = case(
            (
                Attack.attack_command_id.is_not(None),
                Attack.attack_command_id,
            ),
            else_=cast(Attack.id, String),
        )
        successful_commands = func.count(func.distinct(command_key))
        total_damage = func.coalesce(func.sum(Attack.result_damage), 0)
        rows = (
            await session.execute(
                select(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                    successful_commands,
                    total_damage,
                )
                .join(Attack, Attack.attacker_id == User.id)
                .where(
                    User.is_active.is_(True),
                    Attack.status == AttackStatus.RESOLVED,
                    Attack.is_successful.is_(True),
                )
                .group_by(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                )
                .order_by(
                    successful_commands.desc(),
                    total_damage.desc(),
                    User.id.asc(),
                )
                .limit(limit)
            )
        ).all()
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row) -> LeaderboardRecord:
        return LeaderboardRecord(
            user_id=int(row[0]),
            first_name=row[1],
            last_name=row[2],
            username=row[3],
            primary_value=int(row[4] or 0),
            secondary_value=int(row[5] or 0),
        )
