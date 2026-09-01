from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import LibraryCallback
from app.bot.handlers import library
from app.core.enums import QuestionScope, QuestionStatus
from app.models.question import Question


def message(**overrides):
    values = {
        "from_user": SimpleNamespace(id=42),
        "answer": AsyncMock(),
        "text": "4",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_library_menu_is_shown_from_main_menu_button():
    target = message(text="کتابخانه")
    state = AsyncMock()

    await library.library_handler(target, state)

    state.clear.assert_awaited_once()
    target.answer.assert_awaited_once()
    keyboard = target.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "library:daily"
    assert len(keyboard.inline_keyboard) == 1


@pytest.mark.asyncio
async def test_daily_button_shows_active_question_and_starts_answer_state(monkeypatch):
    question = Question(
        id=10,
        scope=QuestionScope.DAILY,
        question_text="۲ + ۲؟",
        correct_answer="4",
        status=QuestionStatus.ACTIVE,
    )
    monkeypatch.setattr(
        library.question_service,
        "get_active_daily_question",
        AsyncMock(return_value=question),
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    state = AsyncMock()

    await library.library_callback_handler(
        callback,
        LibraryCallback(action="daily"),
        AsyncMock(),
        state,
    )

    state.set_state.assert_awaited_once_with(library.LibraryState.waiting_daily_answer)
    state.update_data.assert_awaited_once_with(question_id=10)
    callback.message.edit_text.assert_awaited_once()
    assert "۲ + ۲؟" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_daily_answer_handler_calls_service_and_clears_state(monkeypatch):
    target = message()
    state = AsyncMock()
    state.get_data.return_value = {"question_id": 10}
    monkeypatch.setattr(
        library.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        library.question_service,
        "answer_daily_question",
        AsyncMock(
            return_value=SimpleNamespace(
                correct=True,
                reward=None,
            )
        ),
    )

    await library.daily_answer_handler(target, state, AsyncMock())

    library.question_service.answer_daily_question.assert_awaited_once()
    assert "درست" in target.answer.await_args.args[0]
    state.clear.assert_awaited_once()
