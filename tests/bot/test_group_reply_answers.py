from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import library
from app.core.enums import ResourceType
from app.services.library_errors import DuplicateAnswer, QuestionAlreadyAnswered


def reply_message(text: str = "تهران") -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=42, first_name="آرش", last_name=None),
        message_id=701,
        text=text,
        chat=SimpleNamespace(id=-100123, type="supergroup"),
        reply_to_message=SimpleNamespace(message_id=700, delete=AsyncMock()),
        answer=AsyncMock(),
        delete=AsyncMock(),
    )


def test_correct_answer_banner_uses_the_awarded_resource_icons() -> None:
    result = SimpleNamespace(
        rewards=tuple(
            SimpleNamespace(resource_type=resource, amount=amount)
            for resource, amount in (
                (ResourceType.COIN, 100),
                (ResourceType.DIAMOND, 5),
                (ResourceType.BANANA, 2),
            )
        )
    )

    text = library._group_correct_banner(
        SimpleNamespace(first_name="AtilA", last_name=None), result
    )

    assert "AtilA" in text
    assert "100 سکه طلا" in text
    assert "tg://emoji?id=5825699971076202989" in text
    assert "tg://emoji?id=5825753314570018832" in text
    assert "tg://emoji?id=5902520589356113908" in text


@pytest.mark.asyncio
async def test_group_reply_to_question_message_is_answered(monkeypatch) -> None:
    message = reply_message()
    publication = SimpleNamespace(id=99, question_id=10, group_id=3)
    monkeypatch.setattr(
        library.question_service,
        "get_group_question_by_message",
        AsyncMock(return_value=publication),
    )
    monkeypatch.setattr(
        library.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    answer = AsyncMock(return_value=SimpleNamespace(correct=True, reward=None))
    monkeypatch.setattr(library.question_service, "answer_group_question", answer)

    session = SimpleNamespace(commit=AsyncMock())
    await library.group_reply_answer_handler(message, session)

    answer.assert_awaited_once()
    assert "پاسخ صحیح داده شد" in message.answer.await_args.args[0]
    assert "tg://emoji?id=5915892656499597169" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_to_message_id"] == 701
    message.delete.assert_awaited_once()
    message.reply_to_message.delete.assert_awaited_once()
    assert session.commit.await_count == 2
    assert publication.telegram_message_id is None


@pytest.mark.asyncio
async def test_wrong_group_reply_is_reported_and_question_remains(monkeypatch) -> None:
    message = reply_message("مشهد")
    publication = SimpleNamespace(id=99, question_id=10, group_id=3)
    monkeypatch.setattr(
        library.question_service,
        "get_group_question_by_message",
        AsyncMock(return_value=publication),
    )
    monkeypatch.setattr(
        library.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        library.question_service,
        "answer_group_question",
        AsyncMock(return_value=SimpleNamespace(correct=False)),
    )

    await library.group_reply_answer_handler(
        message, SimpleNamespace(commit=AsyncMock())
    )

    assert "اشتباه جواب دادی" in message.answer.await_args.args[0]
    message.delete.assert_awaited_once()
    message.reply_to_message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeat_wrong_answer_is_blocked_for_that_user(monkeypatch) -> None:
    message = reply_message("تهران")
    monkeypatch.setattr(
        library.question_service,
        "get_group_question_by_message",
        AsyncMock(return_value=SimpleNamespace(question_id=10, group_id=3)),
    )
    monkeypatch.setattr(
        library.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        library.question_service,
        "answer_group_question",
        AsyncMock(side_effect=DuplicateAnswer),
    )

    await library.group_reply_answer_handler(
        message, SimpleNamespace(commit=AsyncMock())
    )

    assert "قبلاً" in message.answer.await_args.args[0]
    message.delete.assert_awaited_once()
    message.reply_to_message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_group_reply_does_not_create_group_spam(monkeypatch) -> None:
    message = reply_message("مشهد")
    publication = SimpleNamespace(id=99, question_id=10, group_id=3)
    monkeypatch.setattr(
        library.question_service,
        "get_group_question_by_message",
        AsyncMock(return_value=publication),
    )
    monkeypatch.setattr(
        library.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(id=8)),
    )
    monkeypatch.setattr(
        library.question_service,
        "answer_group_question",
        AsyncMock(side_effect=QuestionAlreadyAnswered),
    )
    await library.group_reply_answer_handler(message, AsyncMock())

    message.answer.assert_not_awaited()
