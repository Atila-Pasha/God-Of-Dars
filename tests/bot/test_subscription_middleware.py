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
