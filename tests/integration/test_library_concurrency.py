import asyncio

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.core.enums import QuestionScope, QuestionStatus, ResourceType
from app.db.session import AsyncSessionLocal
from app.models.answer import Answer
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question
from app.models.resource import Resource
from app.models.reward import Reward
from app.models.transaction import Transaction
from app.models.user import User
from app.services.library_errors import QuestionAlreadyAnswered
from app.services.question_service import QuestionService
from app.services.reward_service import RewardSpec

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"),
    reason="winner concurrency requires PostgreSQL",
)


@pytest.mark.asyncio
async def test_concurrent_group_answers_have_exactly_one_winner():
    async with AsyncSessionLocal() as setup_session:
        async with setup_session.begin():
            group = Group(
                telegram_chat_id=-910000001,
                title="library concurrency test",
            )
            first_user = User(
                telegram_user_id=910000001,
                first_name="first",
            )
            second_user = User(
                telegram_user_id=910000002,
                first_name="second",
            )
            first_user.resources = Resource()
            second_user.resources = Resource()
            question = Question(
                scope=QuestionScope.GROUP,
                question_text="Concurrency test",
                correct_answer="winner",
            )
            publication = GroupQuestion(
                group=group,
                question=question,
                status=QuestionStatus.ACTIVE,
            )
            setup_session.add_all([group, first_user, second_user, question, publication])
        group_id = group.id
        question_id = question.id
        first_user_id = first_user.id
        second_user_id = second_user.id

    async def submit(user_id: int):
        async with AsyncSessionLocal() as session:
            try:
                async with session.begin():
                    return await QuestionService(
                        group_reward=RewardSpec(ResourceType.COIN, 1)
                    ).answer_group_question(
                        session,
                        user_id,
                        question_id,
                        group_id,
                        "winner",
                    )
            except QuestionAlreadyAnswered as exc:
                return exc

    try:
        results = await asyncio.gather(
            submit(first_user_id),
            submit(second_user_id),
        )
        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert sum(isinstance(result, QuestionAlreadyAnswered) for result in results) == 1

        async with AsyncSessionLocal() as verify_session:
            answers = (
                (
                    await verify_session.execute(
                        Answer.__table__.select().where(
                            Answer.question_id == question_id,
                            Answer.group_id == group_id,
                            Answer.is_valid.is_(True),
                        )
                    )
                )
                .mappings()
                .all()
            )
            assert len(answers) == 1
            rewards = (
                (
                    await verify_session.execute(
                        Reward.__table__.select().where(
                            Reward.source == "GROUP_QUESTION",
                            Reward.reference_type == "ANSWER",
                            Reward.user_id.in_([first_user_id, second_user_id]),
                        )
                    )
                )
                .mappings()
                .all()
            )
            assert len(rewards) == 1
    finally:
        async with AsyncSessionLocal() as cleanup_session, cleanup_session.begin():
            await cleanup_session.execute(
                delete(Transaction).where(
                    Transaction.user_id.in_([first_user_id, second_user_id])
                )
            )
            await cleanup_session.execute(
                delete(Reward).where(
                    Reward.user_id.in_([first_user_id, second_user_id])
                )
            )
            await cleanup_session.execute(
                delete(Answer).where(Answer.question_id == question_id)
            )
            await cleanup_session.execute(
                delete(GroupQuestion).where(GroupQuestion.question_id == question_id)
            )
            await cleanup_session.execute(
                delete(Question).where(Question.id == question_id)
            )
            await cleanup_session.execute(
                delete(User).where(User.id.in_([first_user_id, second_user_id]))
            )
            await cleanup_session.execute(delete(Group).where(Group.id == group_id))
