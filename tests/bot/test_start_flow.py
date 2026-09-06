from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import User as TelegramUser

from app.bot.handlers import start
from app.services.subscription_service import MembershipCheckError


def telegram_user() -> TelegramUser:
    return TelegramUser(id=42, is_bot=False, first_name="Ali", username="ali")


@pytest.mark.asyncio
async def test_start_member_initializes_user_and_shows_menu(monkeypatch) -> None:
    message = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        answer=AsyncMock(),
    )
    session = AsyncMock()
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=True)
    )
    initialize = AsyncMock()
    monkeypatch.setattr(start.user_service, "get_or_create_from_telegram", initialize)

    await start.start_handler(message, session)

    initialize.assert_awaited_once_with(session, message.from_user)
    assert message.answer.await_count == 2
    assert "راهنمای کدام بخش" in message.answer.await_args_list[1].args[0]
    keyboard = message.answer.await_args_list[0].kwargs["reply_markup"]
    assert keyboard.is_persistent is False
    assert keyboard.resize_keyboard is True
    assert keyboard.keyboard


@pytest.mark.asyncio
async def test_start_non_member_shows_join_keyboard(monkeypatch) -> None:
    message = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        start.subscription_service, "channels", ("example_channel",)
    )

    await start.start_handler(message, AsyncMock())

    assert "عضو کانال" in message.answer.await_args.args[0]
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert (
        keyboard.inline_keyboard[0][0].url
        == start.subscription_service.channel_url(
            start.subscription_service.channels[0]
        )
    )
    assert keyboard.inline_keyboard[1][0].callback_data == "channel:check"


@pytest.mark.asyncio
async def test_start_banned_user_is_blocked(monkeypatch) -> None:
    message = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        answer=AsyncMock(),
    )
    session = AsyncMock()
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=True)
    )
    banned_user = SimpleNamespace(is_active=False)
    monkeypatch.setattr(
        start.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=banned_user),
    )

    await start.start_handler(message, session)

    assert "مسدود" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_main_menu_message_for_unimplemented_feature_is_safe(
    monkeypatch,
) -> None:
    message = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        text="کتابخانه",
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=True)
    )

    await start.main_menu_handler(message)

    assert "به‌زودی" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_markup"].is_persistent is False


@pytest.mark.asyncio
async def test_membership_callback_before_join_keeps_join_prompt(monkeypatch) -> None:
    callback = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=False)
    )

    await start.check_membership_handler(callback, AsyncMock())

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "عضویت" in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_membership_callback_after_join_shows_menu(monkeypatch) -> None:
    callback = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )
    session = AsyncMock()
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=True)
    )
    initialize = AsyncMock()
    monkeypatch.setattr(start.user_service, "get_or_create_from_telegram", initialize)

    await start.check_membership_handler(callback, session)

    initialize.assert_awaited_once_with(session, callback.from_user)
    assert callback.answer.await_args.args[0] == "عضویت تأیید شد."
    assert callback.message.answer.await_count == 2
    assert "راهنمای کدام بخش" in callback.message.answer.await_args_list[1].args[0]
    assert (
        callback.message.answer.await_args_list[0].kwargs["reply_markup"].is_persistent
        is False
    )


@pytest.mark.asyncio
async def test_membership_callback_for_banned_user_blocks_access(monkeypatch) -> None:
    callback = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )
    session = AsyncMock()
    monkeypatch.setattr(
        start.subscription_service, "is_member", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        start.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(is_active=False)),
    )

    await start.check_membership_handler(callback, session)

    callback.answer.assert_awaited_once()
    assert "مسدود" in callback.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_membership_callback_api_error_does_not_expose_exception(
    monkeypatch,
) -> None:
    callback = SimpleNamespace(
        from_user=telegram_user(),
        bot=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        start.subscription_service,
        "is_member",
        AsyncMock(side_effect=MembershipCheckError),
    )

    await start.check_membership_handler(callback, AsyncMock())

    callback.answer.assert_awaited_once()
    assert "امکان‌پذیر نیست" in callback.answer.await_args.args[0]
