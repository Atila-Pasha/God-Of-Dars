from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.subscription_service import (
    MembershipCheckError,
    SubscriptionService,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["creator", "administrator", "member"])
async def test_active_membership_statuses_are_allowed(status: str) -> None:
    bot = AsyncMock()
    bot.get_chat_member.return_value = SimpleNamespace(status=status)
    service = SubscriptionService("@AtA_401")

    assert await service.is_member(bot, 42) is True
    bot.get_chat_member.assert_awaited_once_with(chat_id="@AtA_401", user_id=42)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_inactive_membership_statuses_are_rejected(status: str) -> None:
    bot = AsyncMock()
    bot.get_chat_member.return_value = SimpleNamespace(status=status)

    assert await SubscriptionService("@AtA_401").is_member(bot, 42) is False


@pytest.mark.asyncio
async def test_user_must_be_member_of_all_required_channels() -> None:
    bot = AsyncMock()
    bot.get_chat_member.side_effect = [
        SimpleNamespace(status="member"),
        SimpleNamespace(status="left"),
    ]

    result = await SubscriptionService(("@first", "@second")).is_member(bot, 42)

    assert result is False
    assert bot.get_chat_member.await_args_list[0].kwargs == {
        "chat_id": "@first",
        "user_id": 42,
    }
    assert bot.get_chat_member.await_args_list[1].kwargs == {
        "chat_id": "@second",
        "user_id": 42,
    }


@pytest.mark.asyncio
async def test_empty_required_channels_allow_access_without_api_call() -> None:
    bot = AsyncMock()

    assert await SubscriptionService().is_member(bot, 42) is True
    bot.get_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_membership_api_failure_is_wrapped() -> None:
    bot = AsyncMock()
    bot.get_chat_member.side_effect = RuntimeError("internal details")

    with pytest.raises(MembershipCheckError):
        await SubscriptionService("@AtA_401").is_member(bot, 42)
