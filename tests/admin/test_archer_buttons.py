from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin import handlers, keyboards
from app.bot.custom_emojis import _decorate_markup


def test_archer_menu_labels_match_the_text_telegram_sends() -> None:
    markup = keyboards.content_menu()
    _decorate_markup({"reply_markup": markup})
    labels = [button.text for row in markup.keyboard for button in row]

    assert "کماندارها" in labels
    assert "پک‌های تیر" in labels
    assert "کماندارها" in handlers.button_labels("🏹 کماندارها")
    assert "پک‌های تیر" in handlers.button_labels("🎯 پک‌های تیر")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "heading"),
    [("کماندارها", "کماندارها"), ("پک‌های تیر", "پک‌های تیر")],
)
async def test_archer_lists_open_from_premium_buttons(
    monkeypatch, label: str, heading: str
) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    message = SimpleNamespace(text=label, answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())
    session = SimpleNamespace(scalars=AsyncMock(return_value=[]))

    await handlers.archer_admin_list(message, state, session)

    state.clear.assert_awaited_once()
    assert heading in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["➕ کماندار جدید", "➕ پک تیر جدید"])
async def test_archer_create_buttons_start_the_form(monkeypatch, label: str) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    message = SimpleNamespace(text=label, answer=AsyncMock())
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    await handlers.archer_admin_start(message, state)

    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once()
    message.answer.assert_awaited_once()
