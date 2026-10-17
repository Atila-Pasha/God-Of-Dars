import asyncio
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.enums import QuestionScope
from app.db.session import AsyncSessionLocal, engine
from app.models.answer import Answer
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question
from app.models.user import User
from app.services.library_errors import DuplicateAnswer
from app.services.question_service import QuestionService

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"),
    reason="cross-group attempt locking requires PostgreSQL",
)


@pytest.mark.asyncio
async def test_one_group_question_attempt_covers_every_group_even_concurrently() -> (
    None
):
    await engine.dispose()
    suffix = uuid.uuid4().int % 1_000_000_000
    async with AsyncSessionLocal() as session, session.begin():
        groups = [
            Group(telegram_chat_id=-(suffix * 10 + i), title=f"question {i}")
            for i in (1, 2)
        ]
        users = [
            User(telegram_user_id=suffix * 10 + i, first_name=f"player {i}")
            for i in (1, 2)
        ]
        question = Question(
            scope=QuestionScope.GROUP,
            question_text="پایتخت ایران؟",
            correct_answer="تهران",
        )
        session.add_all([*groups, *users, question])
        session.add_all(
            GroupQuestion(group=group, question=question) for group in groups
        )
    group_ids = [group.id for group in groups]
    user_ids = [user.id for user in users]
    question_id = question.id

    try:
        async with AsyncSessionLocal() as session, session.begin():
            wrong = await QuestionService().answer_group_question(
                session, user_ids[0], question_id, group_ids[0], "مشهد"
            )
            assert wrong.correct is False

        async with AsyncSessionLocal() as session:
            with pytest.raises(DuplicateAnswer):
                await QuestionService().answer_group_question(
                    session, user_ids[0], question_id, group_ids[1], "تهران"
                )

        async def answer(group_id: int):
            try:
                async with AsyncSessionLocal() as session, session.begin():
                    return await QuestionService().answer_group_question(
                        session, user_ids[1], question_id, group_id, "تهران"
                    )
            except DuplicateAnswer as exc:
                return exc

        results = await asyncio.gather(*(answer(group_id) for group_id in group_ids))
        assert sum(isinstance(result, DuplicateAnswer) for result in results) == 1
        assert sum(getattr(result, "correct", False) for result in results) == 1

        async with AsyncSessionLocal() as session:
            answers = list(
                await session.scalars(
                    select(Answer).where(Answer.question_id == question_id)
                )
            )
            assert len(answers) == 2
            assert {answer.user_id for answer in answers} == set(user_ids)
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Answer).where(Answer.question_id == question_id)
            )
            await session.execute(
                delete(GroupQuestion).where(GroupQuestion.question_id == question_id)
            )
            await session.execute(delete(Question).where(Question.id == question_id))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.execute(delete(Group).where(Group.id.in_(group_ids)))
        await engine.dispose()
