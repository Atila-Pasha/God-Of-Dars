from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import QuestionScope, QuestionStatus
from app.models.answer import Answer
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question


class QuestionRepository:
    async def create_question(
        self,
        session: AsyncSession,
        *,
        question_text: str,
        correct_answer: str,
        scope: QuestionScope,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
    ) -> Question:
        question = Question(
            question_text=question_text,
            correct_answer=correct_answer,
            scope=scope,
            expires_at=expires_at,
            published_at=published_at,
        )
        session.add(question)
        await session.flush()
        return question

    async def get_by_id(
        self, session: AsyncSession, question_id: int, *, for_update: bool = False
    ) -> Question | None:
        statement = select(Question).where(Question.id == question_id)
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_daily(
        self, session: AsyncSession, *, now: datetime
    ) -> Question | None:
        result = await session.execute(
            select(Question)
            .where(
                Question.scope == QuestionScope.DAILY,
                Question.status == QuestionStatus.ACTIVE,
                (Question.expires_at.is_(None) | (Question.expires_at > now)),
            )
            .order_by(Question.created_at.desc(), Question.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_group(
        self, session: AsyncSession, group_id: int
    ) -> Group | None:
        result = await session.execute(select(Group).where(Group.id == group_id))
        return result.scalar_one_or_none()

    async def get_active_group_question_for_chat(
        self,
        session: AsyncSession,
        *,
        telegram_chat_id: int,
        now: datetime,
    ) -> GroupQuestion | None:
        expiration = func.coalesce(GroupQuestion.expires_at, Question.expires_at)
        result = await session.execute(
            select(GroupQuestion)
            .join(GroupQuestion.group)
            .join(GroupQuestion.question)
            .where(
                Group.telegram_chat_id == telegram_chat_id,
                Group.is_active.is_(True),
                Question.scope == QuestionScope.GROUP,
                GroupQuestion.status == QuestionStatus.ACTIVE,
                (expiration.is_(None) | (expiration > now)),
            )
            .options(selectinload(GroupQuestion.question))
            .order_by(GroupQuestion.published_at.desc(), GroupQuestion.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_group_question(
        self,
        session: AsyncSession,
        *,
        question: Question,
        group: Group,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
    ) -> GroupQuestion:
        publication = GroupQuestion(
            question=question,
            group=group,
            expires_at=expires_at,
            published_at=published_at,
        )
        session.add(publication)
        await session.flush()
        return publication

    async def get_group_question(
        self,
        session: AsyncSession,
        *,
        question_id: int,
        group_id: int,
        for_update: bool = False,
    ) -> GroupQuestion | None:
        statement = (
            select(GroupQuestion)
            .where(
                GroupQuestion.question_id == question_id,
                GroupQuestion.group_id == group_id,
            )
            .options(selectinload(GroupQuestion.question))
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def has_active_group_publications(
        self,
        session: AsyncSession,
        *,
        question_id: int,
        exclude_id: int,
    ) -> bool:
        result = await session.execute(
            select(func.count(GroupQuestion.id)).where(
                GroupQuestion.question_id == question_id,
                GroupQuestion.id != exclude_id,
                GroupQuestion.status == QuestionStatus.ACTIVE,
            )
        )
        return bool(result.scalar_one())

    async def get_daily_answer(
        self,
        session: AsyncSession,
        *,
        question_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> Answer | None:
        statement = select(Answer).where(
            Answer.question_id == question_id,
            Answer.user_id == user_id,
            Answer.group_id.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_group_answer(
        self,
        session: AsyncSession,
        *,
        question_id: int,
        group_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> Answer | None:
        statement = select(Answer).where(
            Answer.question_id == question_id,
            Answer.group_id == group_id,
            Answer.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()
