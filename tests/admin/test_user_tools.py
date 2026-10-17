from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from admin import handlers, keyboards
from app.models.resource import Resource
from app.services.admin_service import AdminService


def test_user_card_exposes_direct_message_and_resource_actions() -> None:
    callbacks = {
        button.callback_data
        for row in keyboards.user_actions(42, True).inline_keyboard
        for button in row
    }
    assert {"user:message:42", "user:resources:42"} <= callbacks


@pytest.mark.asyncio
async def test_admin_grant_accepts_banana_and_records_a_transaction() -> None:
    user = SimpleNamespace(id=42, resources=Resource(coin=10, diamond=20, banana=30))
    result = SimpleNamespace(scalar_one_or_none=lambda: user)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
        add=Mock(),
    )

    saved = await AdminService().add_resources(
        session, 42, coin=0, diamond=0, banana=15
    )

    assert saved is user
    assert user.resources.banana == 45
    transaction = session.add.call_args.args[0]
    assert (transaction.reason, transaction.amount, transaction.balance_after) == (
        "ADMIN_GRANT",
        15,
        45,
    )


@pytest.mark.asyncio
async def test_resource_form_asks_for_banana_after_diamonds(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    message = SimpleNamespace(text="5", answer=AsyncMock())
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())

    await handlers.resource_diamond(message, state, SimpleNamespace())

    state.update_data.assert_awaited_once_with(diamond=5)
    state.set_state.assert_awaited_once_with(handlers.UserStates.resource_banana)
    assert "موز" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_direct_message_targets_selected_user_only(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    user = SimpleNamespace(telegram_user_id=12345)
    monkeypatch.setattr(handlers.service, "get_user", AsyncMock(return_value=user))
    bot = AsyncMock()
    bot.__aenter__.return_value = bot
    monkeypatch.setattr(handlers, "Bot", lambda **_: bot)
    monkeypatch.setattr(handlers, "AiohttpSession", lambda **_: object())
    message = SimpleNamespace(text="سلام", photo=None, answer=AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"user_id": 42}), clear=AsyncMock()
    )

    await handlers.user_direct_message(message, state, SimpleNamespace())

    bot.send_message.assert_awaited_once_with(chat_id=12345, text="سلام")
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_level_decrease_form_updates_selected_user(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    user = SimpleNamespace(id=42, level=8, is_active=True)
    decrease = AsyncMock(return_value=(user, 10))
    monkeypatch.setattr(handlers.service, "decrease_user_level", decrease)
    monkeypatch.setattr(handlers, "user_text", lambda _: "user card")
    message = SimpleNamespace(text="2", answer=AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"user_id": 42}), clear=AsyncMock()
    )
    session = SimpleNamespace()

    await handlers.user_level_decrease(message, state, session)

    decrease.assert_awaited_once_with(session, 42, 2)
    state.clear.assert_awaited_once()
    assert "از 10 به 8" in message.answer.await_args_list[0].args[0]
