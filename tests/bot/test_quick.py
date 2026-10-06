from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.banners import MARKDOWN_V2
from app.bot.handlers import quick
from app.services.slogan_service import SloganClaim


@pytest.mark.asyncio
async def test_god_reply_uses_supplied_premium_emoji(monkeypatch) -> None:
    message = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(quick, "choice", lambda replies: replies[0])

    await quick.god_reply_handler(message)

    text = message.answer.await_args.args[0]
    assert "6039496463749223185" in text
    assert message.answer.await_args.kwargs["parse_mode"] == MARKDOWN_V2
    assert len(quick.GOD_REPLIES) >= 15
    assert {reply[0] for reply in quick.GOD_REPLIES} == {
        "6039496463749223185",
        "5388834817058035756",
        "5825961702088254236",
        "5834681271678144844",
        "5834791394639614640",
    }


@pytest.mark.asyncio
async def test_slogan_reply_reports_reward_and_cooldown(monkeypatch) -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=42), answer=AsyncMock())
    claim = AsyncMock(side_effect=[SloganClaim(2), SloganClaim(2, 59 * 60 + 30)])
    monkeypatch.setattr(quick.slogan_service, "claim", claim)

    await quick.slogan_handler(message, AsyncMock())
    await quick.slogan_handler(message, AsyncMock())

    first, second = [call.args[0] for call in message.answer.await_args_list]
    assert "2 موز" in first
    assert "59:30" in second
    assert all(
        call.kwargs["parse_mode"] == MARKDOWN_V2
        for call in message.answer.await_args_list
    )
