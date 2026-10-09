from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin import handlers
from app.bot.callbacks_chance import ChanceBoxCaptchaCallback
from app.bot.custom_emojis import _persist_group_message
from app.core.enums import ResourceType


@pytest.mark.asyncio
@pytest.mark.parametrize("sticker", [None, "file-id"])
async def test_group_box_is_a_photo_with_nine_position_buttons(
    monkeypatch, sticker
) -> None:
    group = SimpleNamespace(id=5, telegram_chat_id=-4)
    box = SimpleNamespace(
        id=7,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        telegram_message_id=0,
        sticker_message_id=None,
    )

    async def send_sticker(*_args):
        assert _persist_group_message.get() is True
        return SimpleNamespace(message_id=54)

    bot = SimpleNamespace(
        send_photo=AsyncMock(return_value=SimpleNamespace(message_id=55)),
        send_sticker=AsyncMock(side_effect=send_sticker),
    )

    class BotContext:
        async def __aenter__(self):
            return bot

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(handlers, "allowed", lambda _message: True)
    monkeypatch.setattr(handlers, "_sticker_value", lambda _message: sticker)
    monkeypatch.setattr(
        handlers.group_repository,
        "list_active",
        AsyncMock(return_value=[group]),
    )
    monkeypatch.setattr(
        handlers.chance_service,
        "box_captcha",
        lambda: (b"\x89PNG\r\n\x1a\n", "5", tuple("123456789")),
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
    assert create_box.await_args.kwargs["captcha_answer"] == "5"
    bot.send_photo.assert_awaited_once()
    rows = bot.send_photo.await_args.kwargs["reply_markup"].inline_keyboard
    assert [len(row) for row in rows] == [3, 3, 3]
    buttons = [button for row in rows for button in row]
    assert [button.text for button in buttons] == list("123456789")
    assert [
        ChanceBoxCaptchaCallback.unpack(button.callback_data).answer
        for button in buttons
    ] == list("123456789")
    assert "جعبه شانس" in bot.send_photo.await_args.kwargs["caption"]
    assert "نماد متفاوت" in bot.send_photo.await_args.kwargs["caption"]
    assert box.telegram_message_id == 55
    assert box.sticker_message_id == (54 if sticker else None)
    assert bot.send_sticker.await_count == (1 if sticker else 0)
