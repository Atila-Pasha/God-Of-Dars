from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from app.bot.callbacks import ArcherCallback
from app.bot.handlers import archers
from app.bot.handlers.archers import show_menu
from app.bot.keyboards.school import school_archers_keyboard
from app.core.enums import ResourceType


@pytest.mark.asyncio
async def test_buffet_archer_menu_only_offers_purchases() -> None:
    message = AsyncMock()

    await show_menu(message, AsyncMock(), 1)

    markup = message.answer.await_args.kwargs["reply_markup"]
    actions = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert actions == ["archer_shop:archers:0", "archer_shop:packs:0"]
    assert "مدرسه من" in message.answer.await_args.args[0]


def test_school_archer_menu_offers_management() -> None:
    markup = school_archers_keyboard(42, has_arrows=True)
    actions = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert actions == [
        "archer_shop:upgrade:42",
        "archer_shop:sell:42",
        "archer_shop:equip:0",
        "school:school",
    ]


@pytest.mark.asyncio
async def test_archer_callback_banners_edit_the_same_message(monkeypatch) -> None:
    message = AsyncMock()
    edit = AsyncMock()
    monkeypatch.setattr(archers, "safe_edit_text", edit)
    markup = archers.keyboard([[archers.button("بازگشت", "menu")]])

    await archers.banner(message, "🏹 خرید کماندار", reply_markup=markup)

    edit.assert_awaited_once()
    assert edit.await_args.args[0] is message
    assert edit.await_args.kwargs["reply_markup"] is markup
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_buffet_entry_still_sends_one_new_message(monkeypatch) -> None:
    message = AsyncMock()
    edit = AsyncMock()
    monkeypatch.setattr(archers, "safe_edit_text", edit)

    await show_menu(message, AsyncMock(), 1)

    message.answer.assert_awaited_once()
    edit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["menu", "archers", "packs", "upgrade", "sell"])
async def test_archer_button_updates_its_message(monkeypatch, action: str) -> None:
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=42, type="private"),
    )
    target = CallbackQuery(
        id="callback",
        from_user=User(id=42, is_bot=False, first_name="Test"),
        chat_instance="test",
        message=message,
    )
    owned = SimpleNamespace(
        id=7,
        level=1,
        archer=SimpleNamespace(
            name="محسنی",
            power=4,
            purchase_price=80,
            purchase_resource=ResourceType.COIN,
            upgrade_price=2,
            emoji=None,
        ),
    )
    monkeypatch.setattr(
        archers.users,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=10)),
    )
    monkeypatch.setattr(archers.service, "catalog", AsyncMock(return_value=[]))
    monkeypatch.setattr(archers.service, "packs", AsyncMock(return_value=[]))
    monkeypatch.setattr(archers.service, "owned", AsyncMock(return_value=[owned]))
    edit = AsyncMock()
    monkeypatch.setattr(archers, "safe_edit_text", edit)
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())

    await archers.callback(
        target,
        ArcherCallback(
            action=action, item_id=7 if action in {"upgrade", "sell"} else 0
        ),
        AsyncMock(),
    )

    edit.assert_awaited_once()
    assert edit.await_args.args[0] is message
