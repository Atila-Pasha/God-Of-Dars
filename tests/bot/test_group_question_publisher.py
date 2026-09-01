from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.group_question_publisher import GroupQuestionPublisher
from app.core.enums import QuestionScope
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question


@pytest.mark.asyncio
async def test_group_question_publisher_sends_to_every_publication() -> None:
    question = Question(
        id=50,
        scope=QuestionScope.GROUP,
        question_text="پایتخت ایران؟",
        correct_answer="تهران",
    )
    publications = [
        GroupQuestion(
            id=1,
            question=question,
            group=Group(id=10, telegram_chat_id=-10, title="اول"),
        ),
        GroupQuestion(
            id=2,
            question=question,
            group=Group(id=11, telegram_chat_id=-11, title="دوم"),
        ),
    ]
    question_service = SimpleNamespace(
        create_group_question_for_all=AsyncMock(return_value=publications)
    )
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=700))
    )
    session = SimpleNamespace(flush=AsyncMock())

    result = await GroupQuestionPublisher(question_service).create_and_publish(
        bot,
        session,
        question_text=question.question_text,
        correct_answer=question.correct_answer,
    )

    assert result.sent_chat_ids == (-10, -11)
    assert result.failed_chat_ids == ()
    assert session.flush.await_count == 2
    assert "reply_markup" not in bot.send_message.await_args_list[0].kwargs
    assert [
        call.kwargs["chat_id"] for call in bot.send_message.await_args_list
    ] == [-10, -11]
    assert "پایتخت ایران؟" in bot.send_message.await_args_list[0].kwargs["text"]
