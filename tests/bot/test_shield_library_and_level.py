from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import LibraryCallback, LibraryShieldCallback
from app.bot.handlers import library
from app.bot.handlers.library import _shield_library_detail_text, _shield_library_text
from app.bot.keyboards.library import (
    shield_library_detail_keyboard,
    shield_library_keyboard,
)
from app.core.enums import ResourceType
from app.services.shield_service import ShieldService


@pytest.mark.asyncio
async def test_shield_shop_catalog_filters_by_player_level() -> None:
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    await ShieldService().catalog(session, player_level=5)
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "shields.unlock_level <= 5" in sql

    await ShieldService().catalog(session, player_level=None)
    all_statement = session.execute.await_args.args[0]
    all_sql = str(all_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "shields.unlock_level <=" not in all_sql


def test_shield_library_shows_full_details_with_custom_emoji() -> None:
    shield = SimpleNamespace(
        name="سپر زنگ تفریح",
        id=7,
        purchase_resource=ResourceType.COIN,
        purchase_price=120,
        unlock_level=1,
        duration_minutes=30,
        description="محافظت کامل",
    )
    text = _shield_library_detail_text(shield)

    assert "tg://emoji?id=5825861861278490879" in text
    assert "120 طلا" in text
    assert "30 دقیقه" in text
    assert "محافظت کامل" in text
    assert "120 طلا" not in _shield_library_text()
    markup = shield_library_keyboard([shield])
    assert markup.inline_keyboard[0][0].callback_data == "library_shield:view:7"
    assert markup.inline_keyboard[0][0].icon_custom_emoji_id == "5825861861278490879"
    assert (
        shield_library_detail_keyboard().inline_keyboard[0][0].callback_data
        == "library_shield:back:0"
    )


@pytest.mark.asyncio
async def test_shield_library_opens_list_then_selected_detail(monkeypatch) -> None:
    shield = SimpleNamespace(
        id=7,
        name="سپر زنگ تفریح",
        is_active=True,
        purchase_resource=ResourceType.COIN,
        purchase_price=120,
        unlock_level=1,
        duration_minutes=30,
        description="محافظت کامل",
    )
    monkeypatch.setattr(
        library.shield_service, "catalog", AsyncMock(return_value=[shield])
    )
    monkeypatch.setattr(
        library.shield_service, "get_shield", AsyncMock(return_value=shield)
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )

    await library.library_callback_handler(
        callback, LibraryCallback(action="shields"), AsyncMock(), AsyncMock()
    )
    list_markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert list_markup.inline_keyboard[0][0].callback_data == "library_shield:view:7"

    await library.library_shield_callback(
        callback, LibraryShieldCallback(action="view", shield_id=7), AsyncMock()
    )
    assert "محافظت کامل" in callback.message.edit_text.await_args.args[0]
