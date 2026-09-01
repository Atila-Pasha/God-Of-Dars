from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import library
from app.services.library_errors import QuestionAlreadyAnswered


def reply_message(text: str = "تهران") -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=42, first_name="آرش", last_name=None),
        message_id=701,
        text=text,
        chat=SimpleNamespace(id=-100123, type="supergroup"),
        reply_to_message=SimpleNamespace(message_id=700),
        answer=AsyncMock(),
    )


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

    await library.group_reply_answer_handler(message, AsyncMock())

    answer.assert_awaited_once()
    assert "درست" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_to_message_id"] == 701


@pytest.mark.asyncio
async def test_late_group_reply_mentions_the_earlier_answerer(monkeypatch) -> None:
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
    monkeypatch.setattr(
        library.question_service,
        "first_group_answer",
        AsyncMock(
            return_value=SimpleNamespace(
                user=SimpleNamespace(first_name="مهدی", last_name="دلیر")
            )
        ),
    )

    await library.group_reply_answer_handler(message, AsyncMock())

    response = message.answer.await_args.args[0]
    assert "مهدی دلیر" in response
    assert "دیر" in response
    assert message.answer.await_args.kwargs["reply_to_message_id"] == 701
