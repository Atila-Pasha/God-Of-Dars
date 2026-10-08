from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin import handlers
from app.bot.callbacks_chance import ChanceBoxCaptchaCallback
from app.core.enums import ResourceType


@pytest.mark.asyncio
async def test_group_box_is_a_photo_with_three_letter_choices(monkeypatch) -> None:
    group = SimpleNamespace(id=5, telegram_chat_id=-4)
    box = SimpleNamespace(
        id=7,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        telegram_message_id=0,
    )
    bot = SimpleNamespace(
        send_photo=AsyncMock(return_value=SimpleNamespace(message_id=55))
    )

    class BotContext:
        async def __aenter__(self):
            return bot

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(handlers, "allowed", lambda _message: True)
    monkeypatch.setattr(handlers, "_sticker_value", lambda _message: None)
    monkeypatch.setattr(
        handlers.group_repository,
        "list_active",
        AsyncMock(return_value=[group]),
    )
    monkeypatch.setattr(
        handlers.chance_service,
        "box_captcha",
        lambda: (b"\x89PNG\r\n\x1a\n", "NEPR", ("NETR", "NEPR", "NPPR")),
    )
    create_box = AsyncMock(return_value=box)
    monkeypatch.setattr(handlers.chance_service, "create_box", create_box)
    monkeypatch.setattr(handlers, "_main_bot", AsyncMock(return_value=BotContext()))
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "resource": ResourceType.DIAMOND.value,
                "amount": 100,
                "section": 1,
            }
        ),
        clear=AsyncMock(),
    )
    session = SimpleNamespace(commit=AsyncMock())

    await handlers.chance_box_publish(message, state, session)

    create_box.assert_awaited_once()
    assert create_box.await_args.kwargs["captcha_answer"] == "NEPR"
    bot.send_photo.assert_awaited_once()
    buttons = bot.send_photo.await_args.kwargs["reply_markup"].inline_keyboard[0]
    assert len(buttons) == 3
    assert [button.text for button in buttons] == ["NETR", "NEPR", "NPPR"]
    assert [
        ChanceBoxCaptchaCallback.unpack(button.callback_data).answer
        for button in buttons
    ] == ["NETR", "NEPR", "NPPR"]
    assert "جعبه شانس" in bot.send_photo.await_args.kwargs["caption"]
    assert box.telegram_message_id == 55
