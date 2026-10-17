from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin import handlers, keyboards
from app.bot.custom_emojis import _decorate_markup
from app.core.enums import ResourceType


def test_archer_menu_labels_match_the_text_telegram_sends() -> None:
    markup = keyboards.content_menu()
    _decorate_markup({"reply_markup": markup})
    labels = [button.text for row in markup.keyboard for button in row]

    assert "کماندارها" in labels
    assert "پک‌های تیر" in labels
    assert "شوالیه‌ها" in labels
    assert "کماندارها" in handlers.button_labels("🏹 کماندارها")
    assert "پک‌های تیر" in handlers.button_labels("🎯 پک‌های تیر")
    assert "شوالیه‌ها" in handlers.button_labels("⚔️ شوالیه‌ها")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "heading"),
    [("کماندارها", "کماندارها"), ("پک‌های تیر", "پک‌های تیر"), ("شوالیه‌ها", "شوالیه‌ها")],
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
@pytest.mark.parametrize(
    "label", ["➕ کماندار جدید", "➕ پک تیر جدید", "➕ شوالیه جدید"]
)
async def test_archer_create_buttons_start_the_form(monkeypatch, label: str) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    message = SimpleNamespace(text=label, answer=AsyncMock())
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    await handlers.archer_admin_start(message, state)

    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once()
    message.answer.assert_awaited_once()


def test_archer_admin_keyboards_have_all_editable_fields() -> None:
    for kind, fields in (
        ("archer", handlers.ARCHER_FIELDS),
        ("pack", handlers.ARROW_FIELDS),
        ("knight", handlers.KNIGHT_FIELDS),
    ):
        markup = keyboards.archer_edit_fields(kind, 12, fields)
        callbacks = {
            button.callback_data for row in markup.inline_keyboard for button in row
        }
        assert {f"catalog:{kind}:field:12:{field}" for field, _ in fields} <= callbacks
        assert f"catalog:{kind}:open:12" in callbacks
        assert f"catalog:{kind}:currency:COIN" in {
            button.callback_data
            for row in keyboards.archer_currency(kind, create=True).inline_keyboard
            for button in row
        }


@pytest.mark.asyncio
async def test_archer_currency_button_advances_creation(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    monkeypatch.setattr(handlers, "Message", SimpleNamespace)
    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="catalog:pack:currency:DIAMOND", message=message, answer=AsyncMock()
    )
    data = {
        "kind": "pack",
        "index": 4,
        "values": {"name": "تستی", "power": 2, "quantity": 5, "purchase_price": 10},
    }

    async def update_data(**kwargs):
        data.update(kwargs)

    state = SimpleNamespace(
        get_data=AsyncMock(side_effect=lambda: data),
        get_state=AsyncMock(return_value=handlers.ArcherStates.value.state),
        update_data=AsyncMock(side_effect=update_data),
    )
    await handlers.archer_admin_callback(callback, state, SimpleNamespace())

    assert data["index"] == 5
    assert data["values"]["purchase_resource"] == ResourceType.DIAMOND
    assert "سطح بازشدن" in message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_archer_edit_field_opens_button_driven_input(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    monkeypatch.setattr(handlers, "Message", SimpleNamespace)
    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="catalog:archer:field:7:power", message=message, answer=AsyncMock()
    )
    state = SimpleNamespace(
        clear=AsyncMock(), set_state=AsyncMock(), update_data=AsyncMock()
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id=7, name="محسنی"))
    )

    await handlers.archer_admin_callback(callback, state, session)

    state.set_state.assert_awaited_once_with(handlers.ArcherStates.edit_value)
    state.update_data.assert_awaited_once_with(kind="archer", item_id=7, field="power")
    assert "قدرت پایه" in message.edit_text.await_args.args[0]
    assert (
        message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard[-1][0].text
        == "بازگشت"
    )
