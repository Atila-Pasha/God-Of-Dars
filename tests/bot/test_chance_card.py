from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks_chance import ChanceCardCallback
from app.bot.handlers import chance
from app.services.chance_service import WrongCaptcha


@pytest.mark.asyncio
async def test_wrong_math_answer_ends_card_flow_after_one_attempt(monkeypatch) -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        text="22",
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"card_id": 7}), clear=AsyncMock()
    )
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        chance.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=5)),
    )
    monkeypatch.setattr(
        chance.chance_service,
        "claim_card",
        AsyncMock(side_effect=WrongCaptcha),
    )

    await chance.verify_card(message, state, session)

    session.commit.assert_awaited_once()
    state.clear.assert_awaited_once()
    assert "فقط یک فرصت" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_used_card_button_does_not_prompt_for_another_answer(monkeypatch) -> None:
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(user_id=5, is_claimed=True))
    )
    monkeypatch.setattr(
        chance.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=5)),
    )

    await chance.start_card(callback, ChanceCardCallback(card_id=7), state, session)

    assert "قابل استفاده نیست" in callback.answer.await_args.args[0]
    state.set_state.assert_not_awaited()
    callback.message.answer.assert_not_awaited()
