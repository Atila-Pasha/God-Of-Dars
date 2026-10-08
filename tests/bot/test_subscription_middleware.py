from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.middlewares import subscription
from app.bot.middlewares.subscription import SubscriptionMiddleware


@pytest.mark.asyncio
async def test_non_member_cannot_reach_feature_handler(monkeypatch):
    middleware = SubscriptionMiddleware()
    event = SimpleNamespace(from_user=SimpleNamespace(id=42), bot=SimpleNamespace())
    handler = AsyncMock()
    blocked = AsyncMock()
    monkeypatch.setattr(
        subscription.subscription_service,
        "is_member",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        SubscriptionMiddleware,
        "_is_bypassed",
        staticmethod(lambda event: False),
    )
    monkeypatch.setattr(SubscriptionMiddleware, "_show_join_prompt", blocked)

    await middleware(handler, event, {})

    handler.assert_not_awaited()
    blocked.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_member_is_allowed_to_reach_feature_handler(monkeypatch):
    middleware = SubscriptionMiddleware()
    event = SimpleNamespace(from_user=SimpleNamespace(id=42), bot=SimpleNamespace())
    handler = AsyncMock(return_value="ok")
    monkeypatch.setattr(
        subscription.subscription_service,
        "is_member",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        SubscriptionMiddleware,
        "_is_bypassed",
        staticmethod(lambda event: False),
    )

    result = await middleware(handler, event, {"x": 1})

    assert result == "ok"
    handler.assert_awaited_once_with(event, {"x": 1})


@pytest.mark.asyncio
async def test_membership_is_rechecked_for_every_action(monkeypatch):
    event = SimpleNamespace(from_user=SimpleNamespace(id=42), bot=SimpleNamespace())
    check = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(subscription.subscription_service, "is_member", check)
    monkeypatch.setattr(
        SubscriptionMiddleware, "_is_bypassed", staticmethod(lambda _: False)
    )
    monkeypatch.setattr(SubscriptionMiddleware, "_show_join_prompt", AsyncMock())
    handler = AsyncMock()
    middleware = SubscriptionMiddleware()
    await middleware(handler, event, {})
    await middleware(handler, event, {})
    assert handler.await_count == 1
    assert all(call.kwargs == {"force_refresh": True} for call in check.await_args_list)


@pytest.mark.asyncio
async def test_malformed_active_channel_fails_closed(monkeypatch):
    monkeypatch.setattr(subscription, "_channels_cache", (0, ()))
    monkeypatch.setattr(
        subscription.settings_repository,
        "list_channels",
        AsyncMock(
            return_value=[
                SimpleNamespace(telegram_id=None, username="invalid channel!")
            ]
        ),
    )
    monkeypatch.setattr(
        subscription.settings_repository,
        "get",
        AsyncMock(return_value=SimpleNamespace(is_active=False)),
    )
    with pytest.raises(ValueError, match="Invalid required channel"):
        await subscription.refresh_channels(AsyncMock(), force=True)


def test_start_and_old_buttons_do_not_bypass_gate():
    from datetime import UTC, datetime

    from aiogram.types import CallbackQuery, Chat, Message, User

    user = User(id=42, is_bot=False, first_name="test")
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=42, type="private"),
        from_user=user,
        text="/start",
    )
    assert not SubscriptionMiddleware._is_bypassed(message)
    for data in ("school:main", "channel:forged", "first_login:confirm"):
        callback = CallbackQuery(
            id="test", from_user=user, chat_instance="test", message=message, data=data
        )
        assert not SubscriptionMiddleware._is_bypassed(callback)
