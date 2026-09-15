from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AttackStatus, ResourceType
from app.models.answer import Answer
from app.models.attack import Attack
from app.models.transaction import Transaction
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
        self, session: AsyncSession, *, limit: int, since: datetime
    ) -> list[LeaderboardRecord]:
        earned_xp = func.coalesce(func.sum(Transaction.amount), 0)
        rows = (
            await session.execute(
                select(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                    earned_xp,
                    User.level,
                )
                .join(Transaction, Transaction.user_id == User.id)
                .where(
                    User.is_active.is_(True),
                    Transaction.resource_type == ResourceType.BANANA,
                    Transaction.amount > 0,
                    Transaction.created_at >= since,
                )
                .group_by(
                    User.id,
                    User.first_name,
                    User.last_name,
                    User.username,
                    User.level,
                )
                .order_by(
                    earned_xp.desc(),
                    User.level.desc(),
                    User.id.asc(),
                )
                .limit(limit)
            )
        ).all()
        return [self._record(row) for row in rows]

    async def students(
        self, session: AsyncSession, *, limit: int, since: datetime
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
                .where(
                    User.is_active.is_(True),
                    Answer.answered_at >= since,
                )
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
        self, session: AsyncSession, *, limit: int, since: datetime
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
                    Attack.resolved_at >= since,
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

    async def commander_position(
        self, session: AsyncSession, *, user_id: int, since: datetime
    ) -> tuple[int, LeaderboardRecord] | None:
        earned_xp = func.coalesce(func.sum(Transaction.amount), 0)
        stats = (
            select(
                User.id.label("user_id"),
                User.first_name.label("first_name"),
                User.last_name.label("last_name"),
                User.username.label("username"),
                earned_xp.label("primary_value"),
                User.level.label("secondary_value"),
            )
            .join(Transaction, Transaction.user_id == User.id)
            .where(
                User.is_active.is_(True),
                Transaction.resource_type == ResourceType.BANANA,
                Transaction.amount > 0,
                Transaction.created_at >= since,
            )
            .group_by(
                User.id,
                User.first_name,
                User.last_name,
                User.username,
                User.level,
            )
            .cte("commander_stats")
        )
        ranked = select(
            stats.c.user_id,
            stats.c.first_name,
            stats.c.last_name,
            stats.c.username,
            stats.c.primary_value,
            stats.c.secondary_value,
            func.row_number()
            .over(
                order_by=(
                    stats.c.primary_value.desc(),
                    stats.c.secondary_value.desc(),
                    stats.c.user_id.asc(),
                )
            )
            .label("position"),
        ).cte("ranked_commanders")
        row = (
            await session.execute(select(ranked).where(ranked.c.user_id == user_id))
        ).one_or_none()
        return self._ranked_record(row)

    async def student_position(
        self, session: AsyncSession, *, user_id: int, since: datetime
    ) -> tuple[int, LeaderboardRecord] | None:
        correct_answers = func.count(Answer.id).filter(
            Answer.is_correct.is_(True), Answer.is_valid.is_(True)
        )
        total_answers = func.count(Answer.id)
        stats = (
            select(
                User.id.label("user_id"),
                User.first_name.label("first_name"),
                User.last_name.label("last_name"),
                User.username.label("username"),
                correct_answers.label("primary_value"),
                total_answers.label("secondary_value"),
            )
            .join(Answer, Answer.user_id == User.id)
            .where(
                User.is_active.is_(True),
                Answer.answered_at >= since,
            )
            .group_by(
                User.id,
                User.first_name,
                User.last_name,
                User.username,
            )
            .having(correct_answers > 0)
            .cte("student_stats")
        )
        accuracy = stats.c.primary_value * 1.0 / func.nullif(stats.c.secondary_value, 0)
        ranked = select(
            stats,
            func.row_number()
            .over(
                order_by=(
                    stats.c.primary_value.desc(),
                    accuracy.desc(),
                    stats.c.secondary_value.asc(),
                    stats.c.user_id.asc(),
                )
            )
            .label("position"),
        ).cte("ranked_students")
        row = (
            await session.execute(select(ranked).where(ranked.c.user_id == user_id))
        ).one_or_none()
        return self._ranked_record(row)

    async def fighter_position(
        self, session: AsyncSession, *, user_id: int, since: datetime
    ) -> tuple[int, LeaderboardRecord] | None:
        command_key = case(
            (Attack.attack_command_id.is_not(None), Attack.attack_command_id),
            else_=cast(Attack.id, String),
        )
        successful_commands = func.count(func.distinct(command_key))
        total_damage = func.coalesce(func.sum(Attack.result_damage), 0)
        stats = (
            select(
                User.id.label("user_id"),
                User.first_name.label("first_name"),
                User.last_name.label("last_name"),
                User.username.label("username"),
                successful_commands.label("primary_value"),
                total_damage.label("secondary_value"),
            )
            .join(Attack, Attack.attacker_id == User.id)
            .where(
                User.is_active.is_(True),
                Attack.status == AttackStatus.RESOLVED,
                Attack.is_successful.is_(True),
                Attack.resolved_at >= since,
            )
            .group_by(
                User.id,
                User.first_name,
                User.last_name,
                User.username,
            )
            .cte("fighter_stats")
        )
        ranked = select(
            stats,
            func.row_number()
            .over(
                order_by=(
                    stats.c.primary_value.desc(),
                    stats.c.secondary_value.desc(),
                    stats.c.user_id.asc(),
                )
            )
            .label("position"),
        ).cte("ranked_fighters")
        row = (
            await session.execute(select(ranked).where(ranked.c.user_id == user_id))
        ).one_or_none()
        return self._ranked_record(row)

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

    @classmethod
    def _ranked_record(cls, row) -> tuple[int, LeaderboardRecord] | None:
        if row is None:
            return None
        return int(row[6]), cls._record(row)
