from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.banners import MARKDOWN_V2
from app.bot.handlers import quick
from app.services.slogan_service import SloganClaim


@pytest.mark.asyncio
async def test_god_reply_uses_supplied_premium_emoji(monkeypatch) -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=41), answer=AsyncMock())
    monkeypatch.setattr(quick, "choice", lambda replies: replies[0])

    await quick.god_reply_handler(message)

    text = message.answer.await_args.args[0]
    assert "6039496463749223185" in text
    assert message.answer.await_args.kwargs["parse_mode"] == MARKDOWN_V2
    assert len(quick.GOD_REPLIES) >= 40
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
    claim = AsyncMock(
        side_effect=[SloganClaim(3, current_banana=1069), SloganClaim(3, 59 * 60 + 30)]
    )
    monkeypatch.setattr(quick.slogan_service, "claim", claim)

    await quick.slogan_handler(message, AsyncMock())
    await quick.slogan_handler(message, AsyncMock())

    first, second = [call.args[0] for call in message.answer.await_args_list]
    assert "3 موز" in first
    assert "1,069" in first
    assert "Keep going, commander" in first
    assert "59:30" in second
    assert (
        message.answer.await_args.kwargs["reply_markup"]
        .inline_keyboard[0][0]
        .callback_data
        == "slogan:42"
    )
    assert all(
        call.kwargs["parse_mode"] == MARKDOWN_V2
        for call in message.answer.await_args_list
    )


@pytest.mark.asyncio
async def test_slogan_timer_only_answers_the_claimant(monkeypatch) -> None:
    remaining = AsyncMock(return_value=59 * 60 + 30)
    monkeypatch.setattr(quick.slogan_service, "remaining_seconds", remaining)
    callback = SimpleNamespace(from_user=SimpleNamespace(id=42), answer=AsyncMock())
    data = quick.SloganCallback(user_id=42)

    await quick.slogan_timer_handler(callback, data, AsyncMock())
    assert "59:30" in callback.answer.await_args.args[0]
    callback.from_user.id = 43
    await quick.slogan_timer_handler(callback, data, AsyncMock())
    assert "صاحب شعار" in callback.answer.await_args.args[0]
    remaining.assert_awaited_once()


def test_slogan_lines_do_not_repeat_for_one_user(monkeypatch) -> None:
    monkeypatch.setattr(quick, "choice", lambda values: values[0])
    history = {}
    first_cycle = [
        quick._fresh_choice(quick.SLOGAN_HEADERS, 42, history)
        for _ in quick.SLOGAN_HEADERS
    ]
    assert len(set(first_cycle)) == len(quick.SLOGAN_HEADERS)
    assert quick._fresh_choice(quick.SLOGAN_HEADERS, 42, history) != first_cycle[-1]
    assert quick.SLOGANS == (
        "من خدای درسم",
        "امروز درس رو فتح میکنم",
        "هر روز از دیروز بهترم",
        "با دانش قلعه میسازم",
        "تا آخر مسیر میجنگم",
        "کیری قویم",
        "من خدام",
        "میجنگم",
        "یا خدا",
    )
