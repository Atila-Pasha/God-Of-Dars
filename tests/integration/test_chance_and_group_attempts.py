import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.enums import QuestionScope, QuestionStatus, ResourceType
from app.db.session import AsyncSessionLocal, engine
from app.models.answer import Answer
from app.models.chance_box import ChanceBox
from app.models.chance_card import ChanceCard
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question
from app.models.user import User
from app.services.chance_service import AlreadyClaimed, ChanceService, WrongCaptcha
from app.services.library_errors import DuplicateAnswer
from app.services.question_service import QuestionService
from app.workers.game_message_cleanup import process_due_game_messages

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"),
    reason="attempt persistence requires PostgreSQL",
)


def telegram_id() -> int:
    return uuid.uuid4().int % 1_000_000_000_000


@pytest.fixture(autouse=True)
async def isolate_postgres_connections():
    await engine.dispose()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_wrong_group_answer_blocks_only_its_author() -> None:
    async with AsyncSessionLocal() as session, session.begin():
        group = Group(telegram_chat_id=-telegram_id(), title="attempt test")
        first = User(telegram_user_id=telegram_id(), first_name="first")
        second = User(telegram_user_id=telegram_id(), first_name="second")
        question = Question(
            scope=QuestionScope.GROUP,
            question_text="پایتخت ایران؟",
            correct_answer="تهران",
        )
        publication = GroupQuestion(group=group, question=question)
        session.add_all([group, first, second, question, publication])
    group_id, question_id = group.id, question.id
    first_id, second_id = first.id, second.id
    service = QuestionService()

    try:
        async with AsyncSessionLocal() as session, session.begin():
            wrong = await service.answer_group_question(
                session, first_id, question_id, group_id, "مشهد"
            )
            assert wrong.correct is False

        async with AsyncSessionLocal() as session:
            with pytest.raises(DuplicateAnswer):
                await service.answer_group_question(
                    session, first_id, question_id, group_id, "تهران"
                )

        async with AsyncSessionLocal() as session, session.begin():
            correct = await service.answer_group_question(
                session, second_id, question_id, group_id, "تهران"
            )
            assert correct.correct is True

        async with AsyncSessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(Answer).where(
                            Answer.question_id == question_id,
                            Answer.group_id == group_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 2
            assert sum(answer.is_valid for answer in rows) == 1
            saved = await session.get(GroupQuestion, publication.id)
            assert saved.status is QuestionStatus.ANSWERED
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Answer).where(Answer.question_id == question_id)
            )
            await session.execute(
                delete(GroupQuestion).where(GroupQuestion.question_id == question_id)
            )
            await session.execute(delete(Question).where(Question.id == question_id))
            await session.execute(
                delete(User).where(User.id.in_([first_id, second_id]))
            )
            await session.execute(delete(Group).where(Group.id == group_id))


@pytest.mark.asyncio
async def test_wrong_math_card_answer_is_consumed_without_reward() -> None:
    async with AsyncSessionLocal() as session, session.begin():
        user = User(telegram_user_id=telegram_id(), first_name="card user")
        session.add(user)
    user_id = user.id
    service = ChanceService()

    try:
        async with AsyncSessionLocal() as session, session.begin():
            card = await service.create_card(
                session, user_id, ResourceType.COIN, 100, "21"
            )
        card_id = card.id

        async with AsyncSessionLocal() as session:
            with pytest.raises(WrongCaptcha):
                await service.claim_card(session, card_id, user_id, "22")
            await session.commit()

        async with AsyncSessionLocal() as session:
            saved = await session.get(ChanceCard, card_id)
            assert saved.is_claimed is True
            assert saved.claimed_at is None
            with pytest.raises(AlreadyClaimed):
                await service.claim_card(session, card_id, user_id, "21")
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(ChanceCard).where(ChanceCard.user_id == user_id)
            )
            await session.execute(delete(User).where(User.id == user_id))


@pytest.mark.asyncio
async def test_expired_group_messages_are_deleted_from_persisted_jobs() -> None:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        group = Group(telegram_chat_id=-telegram_id(), title="cleanup test")
        session.add(group)
        await session.flush()
        question = Question(
            scope=QuestionScope.GROUP,
            question_text="سؤال منقضی",
            correct_answer="جواب",
            expires_at=now - timedelta(minutes=1),
        )
        publication = GroupQuestion(
            group=group,
            question=question,
            telegram_message_id=800,
            expires_at=now - timedelta(minutes=1),
        )
        box = ChanceBox(
            group_id=group.id,
            telegram_message_id=801,
            resource_type=ResourceType.COIN,
            amount=100,
            expires_at=now - timedelta(minutes=1),
        )
        group_id = group.id
        session.add_all([question, publication, box])
    question_id, box_id = question.id, box.id
    bot = SimpleNamespace(delete_message=AsyncMock())

    try:
        await process_due_game_messages(bot)

        async with AsyncSessionLocal() as session:
            saved_box = await session.get(ChanceBox, box_id)
            saved_publication = await session.get(GroupQuestion, publication.id)
            assert saved_box.telegram_message_id is None
            assert saved_publication.telegram_message_id is None
            assert saved_publication.status is QuestionStatus.EXPIRED
        assert bot.delete_message.await_count == 2
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(ChanceBox).where(ChanceBox.id == box_id))
            await session.execute(
                delete(GroupQuestion).where(GroupQuestion.question_id == question_id)
            )
            await session.execute(delete(Question).where(Question.id == question_id))
            await session.execute(delete(Group).where(Group.id == group_id))
