from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import custom_emojis
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
        banana_reward=3,
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
    assert [call.kwargs["chat_id"] for call in bot.send_message.await_args_list] == [
        -10,
        -11,
    ]
    assert "پایتخت ایران؟" in bot.send_message.await_args_list[0].kwargs["text"]
    assert "3 موز" in bot.send_message.await_args_list[0].kwargs["text"]
    assert bot.send_message.await_args_list[0].kwargs["parse_mode"] == "MarkdownV2"


def test_group_question_banner_uses_custom_icons_and_spoiler_time() -> None:
    question = Question(
        question_text="کی [آماده] است؟",
        coin_reward=100,
        diamond_reward=100,
        banana_reward=10,
    )

    text = GroupQuestionPublisher._message_text(
        question, datetime(2026, 10, 8, 12, 37, tzinfo=UTC)
    )

    for icon_id in (
        "5917916556758622836",
        "5253742260054409879",
        "5825898080737697438",
        "5235864325540815679",
        "5825832256068918886",
        "5825709849500985213",
        "5825699971076202989",
        "5825753314570018832",
        "5902520589356113908",
        "5825746176334373354",
    ):
        assert f"tg://emoji?id={icon_id}" in text
    assert "*کی \\[آماده\\] است؟*" in text
    assert "> 100 سکه طلا" in text
    assert "> 100 الماس" in text
    assert "> 10 موز" in text
    assert "||16:07||" in text


@pytest.mark.asyncio
async def test_group_question_publication_is_not_scheduled_for_quick_deletion() -> None:
    question = Question(
        id=51,
        scope=QuestionScope.GROUP,
        question_text="سؤال؟",
        correct_answer="جواب",
    )
    publication = GroupQuestion(
        id=3,
        question=question,
        group=Group(id=12, telegram_chat_id=-12, title="گروه"),
    )
    observed = []

    async def send_message(**kwargs):
        observed.append(custom_emojis._persist_group_message.get())
        return SimpleNamespace(message_id=701)

    publisher = GroupQuestionPublisher(
        SimpleNamespace(
            create_group_question_for_all=AsyncMock(return_value=[publication])
        )
    )
    await publisher.create_and_publish(
        SimpleNamespace(send_message=send_message),
        SimpleNamespace(flush=AsyncMock()),
        question_text="سؤال؟",
        correct_answer="جواب",
    )

    assert observed == [True]
    assert custom_emojis._persist_group_message.get() is False
