from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import QuestionScope, QuestionStatus
from app.models.answer import Answer
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question
from app.services.library_errors import (
    DuplicateAnswer,
    InvalidQuestion,
    QuestionAlreadyAnswered,
    QuestionExpired,
    WrongGroup,
)
from app.services.question_service import QuestionService


class FakeQuestionRepository:
    def __init__(self, question: Question, publication: GroupQuestion | None = None):
        self.question = question
        self.publication = publication
        self.daily_answer = None
        self.daily_answers = {}
        self.group_answers = {}
        self.active_publications = False

    async def get_by_id(self, session, question_id, *, for_update=False):
        return self.question if question_id == self.question.id else None

    async def get_daily_answer(self, session, **kwargs):
        return self.daily_answers.get(kwargs["user_id"], self.daily_answer)

    async def get_group_question(self, session, **kwargs):
        if self.publication and kwargs["group_id"] == self.publication.group_id:
            return self.publication
        return None

    async def get_group_answer(self, session, **kwargs):
        return self.group_answers.get(kwargs["user_id"])

    async def has_active_group_publications(self, session, **kwargs):
        return self.active_publications


def daily_question(**overrides) -> Question:
    values = {
        "id": 10,
        "scope": QuestionScope.DAILY,
        "question_text": "۲ + ۲ چند است؟",
        "correct_answer": "4",
        "status": QuestionStatus.ACTIVE,
    }
    values.update(overrides)
    return Question(**values)


def session():
    return SimpleNamespace(add=lambda item: None, flush=AsyncMock())


@pytest.mark.asyncio
async def test_daily_correct_answer_does_not_close_question_for_other_users():
    question = daily_question()
    repository = FakeQuestionRepository(question)
    result = await QuestionService(repository).answer_daily_question(
        session(), 20, question.id, " 4 "
    )

    assert result.correct is True
    assert result.answer.is_valid is True
    assert question.status is QuestionStatus.ACTIVE

    repository.daily_answers[21] = None
    second = await QuestionService(repository).answer_daily_question(
        session(), 21, question.id, "4"
    )

    assert second.correct is True
    assert question.status is QuestionStatus.ACTIVE


@pytest.mark.asyncio
async def test_daily_incorrect_answer_is_persisted_without_reward_or_close():
    question = daily_question()
    service = QuestionService(FakeQuestionRepository(question))
    result = await service.answer_daily_question(session(), 20, question.id, "5")

    assert result.correct is False
    assert result.reward is None
    assert result.answer.is_valid is False
    assert question.status is QuestionStatus.ACTIVE


@pytest.mark.asyncio
async def test_daily_duplicate_answer_is_rejected_before_second_reward():
    question = daily_question()
    repository = FakeQuestionRepository(question)
    repository.daily_answer = Answer(
        id=99, user_id=20, question_id=question.id, answer_content="4", is_correct=True
    )

    with pytest.raises(DuplicateAnswer):
        await QuestionService(repository).answer_daily_question(
            session(), 20, question.id, "4"
        )


@pytest.mark.asyncio
async def test_expired_daily_question_is_marked_expired():
    question = daily_question(
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    with pytest.raises(QuestionExpired):
        await QuestionService(FakeQuestionRepository(question)).answer_daily_question(
            session(), 20, question.id, "4"
        )

    assert question.status is QuestionStatus.EXPIRED


@pytest.mark.asyncio
async def test_invalid_question_scope_is_rejected():
    question = daily_question(scope=QuestionScope.GROUP)

    with pytest.raises(InvalidQuestion):
        await QuestionService(FakeQuestionRepository(question)).answer_daily_question(
            session(), 20, question.id, "4"
        )


@pytest.mark.asyncio
async def test_group_question_creation_builds_a_group_publication():
    repository = AsyncMock()
    group = Group(id=30, telegram_chat_id=-30, title="Group", is_active=True)
    question = Question(
        id=10,
        scope=QuestionScope.GROUP,
        question_text="پایتخت ایران؟",
        correct_answer="تهران",
    )
    publication = GroupQuestion(id=50, question=question, group=group)
    repository.get_group.return_value = group
    repository.create_question.return_value = question
    repository.create_group_question.return_value = publication

    result = await QuestionService(repository).create_group_question(
        session(),
        question_text=question.question_text,
        correct_answer=question.correct_answer,
        group_id=group.id,
    )

    assert result is publication
    repository.create_question.assert_awaited_once()
    repository.create_group_question.assert_awaited_once()


def group_fixture():
    question = Question(
        id=10,
        scope=QuestionScope.GROUP,
        question_text="پایتخت ایران؟",
        correct_answer="تهران",
        status=QuestionStatus.ACTIVE,
    )
    publication = GroupQuestion(
        id=50,
        question=question,
        group=Group(id=30, telegram_chat_id=-30, title="Group"),
        status=QuestionStatus.ACTIVE,
    )
    return question, publication


@pytest.mark.asyncio
async def test_group_wrong_group_is_rejected():
    question, publication = group_fixture()
    repository = FakeQuestionRepository(question, publication)

    with pytest.raises(WrongGroup):
        await QuestionService(repository).answer_group_question(
            session(), 20, question.id, 999, "تهران"
        )


@pytest.mark.asyncio
async def test_group_incorrect_answer_does_not_consume_the_group_question():
    question, publication = group_fixture()
    repository = FakeQuestionRepository(question, publication)
    service = QuestionService(repository)

    first = await service.answer_group_question(
        session(), 20, question.id, publication.group_id, "مشهد"
    )
    assert first.valid is False
    assert publication.status is QuestionStatus.ACTIVE
    assert question.status is QuestionStatus.ACTIVE

    second = await service.answer_group_question(
        session(), 21, question.id, publication.group_id, "تهران"
    )
    assert second.correct is True
    assert publication.status is QuestionStatus.ANSWERED
    assert question.status is QuestionStatus.ANSWERED


@pytest.mark.asyncio
async def test_group_second_user_is_rejected_after_first_valid_answer():
    question, publication = group_fixture()
    repository = FakeQuestionRepository(question, publication)
    service = QuestionService(repository)

    await service.answer_group_question(
        session(), 20, question.id, publication.group_id, "تهران"
    )

    with pytest.raises(QuestionAlreadyAnswered):
        await service.answer_group_question(
            session(), 21, question.id, publication.group_id, "تهران"
        )


@pytest.mark.asyncio
async def test_group_question_is_published_to_every_active_group():
    repository = AsyncMock()
    groups = [
        Group(id=30, telegram_chat_id=-30, title="اول", is_active=True),
        Group(id=31, telegram_chat_id=-31, title="دوم", is_active=True),
    ]
    question = Question(
        id=10,
        scope=QuestionScope.GROUP,
        question_text="پایتخت ایران؟",
        correct_answer="تهران",
    )
    repository.list_active_groups.return_value = groups
    repository.create_question.return_value = question

    async def create_publication(session, *, question, group, **kwargs):
        return GroupQuestion(question=question, group=group)

    repository.create_group_question.side_effect = create_publication

    publications = await QuestionService(repository).create_group_question_for_all(
        session(),
        question_text=question.question_text,
        correct_answer=question.correct_answer,
    )

    assert [publication.group.id for publication in publications] == [30, 31]
    assert repository.create_group_question.await_count == 2
