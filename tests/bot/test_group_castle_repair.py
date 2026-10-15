from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser

from app.bot.callbacks import ConfirmationCallback
from app.bot.handlers import school


def group_message(user_id: int = 91) -> Message:
    return Message.model_construct(
        message_id=123,
        date=0,
        chat=Chat.model_construct(id=-100123, type="supergroup"),
        from_user=TelegramUser.model_construct(
            id=user_id, is_bot=False, first_name="commander"
        ),
        text="تعمیر دژ",
    )


def repair_callback(user_id: int) -> CallbackQuery:
    return CallbackQuery.model_construct(
        id="callback",
        from_user=TelegramUser.model_construct(
            id=user_id, is_bot=False, first_name="commander"
        ),
        chat_instance="group",
        message=group_message(),
    )


@pytest.mark.asyncio
async def test_group_repair_quotes_cost_and_binds_confirmation_to_requester(
    monkeypatch,
) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=7)))
    monkeypatch.setattr(
        school.castle_service.repository,
        "get_by_user",
        AsyncMock(return_value=SimpleNamespace(id=12)),
    )
    monkeypatch.setattr(
        school.castle_service,
        "repair_quote",
        lambda _castle: SimpleNamespace(missing_strength=60, diamond_cost=5),
    )

    await school.group_castle_repair(group_message(), AsyncMock())

    assert "60" in answer.await_args.args[0]
    assert "5" in answer.await_args.args[0]
    button = answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    packed = ConfirmationCallback.unpack(button.callback_data)
    assert packed.action == "castle_repair"
    assert packed.target_id == 91


@pytest.mark.asyncio
async def test_other_group_member_cannot_confirm_castle_repair(monkeypatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    repair = AsyncMock()
    monkeypatch.setattr(school.castle_service, "repair", repair)
    callback = repair_callback(92)

    await school.confirmation_callback_handler(
        callback,
        ConfirmationCallback(action="castle_repair", target_id=91, decision="confirm"),
        AsyncMock(),
    )

    repair.assert_not_awaited()
    assert answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_requester_can_confirm_group_repair(monkeypatch) -> None:
    answer = AsyncMock()
    edit = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    monkeypatch.setattr(Message, "edit_text", edit)
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=7)))
    repair = AsyncMock(return_value=SimpleNamespace(strength=100))
    monkeypatch.setattr(school.castle_service, "repair", repair)
    session = SimpleNamespace(commit=AsyncMock())

    await school.confirmation_callback_handler(
        repair_callback(91),
        ConfirmationCallback(action="castle_repair", target_id=91, decision="confirm"),
        session,
    )

    repair.assert_awaited_once_with(session, 7)
    session.commit.assert_awaited_once()
    assert "100" in edit.await_args.args[0]
    answer.assert_awaited_once_with("دژ تعمیر شد.")
