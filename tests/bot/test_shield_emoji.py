from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin import handlers as admin_handlers
from app.bot.handlers.buffet import _shield_catalog_banner, _shield_purchase_banner
from app.bot.handlers.library import _shield_library_detail_text
from app.bot.keyboards.buffet import shield_catalog_keyboard
from app.bot.keyboards.library import shield_library_keyboard
from app.bot.shield_presentation import shield_button_label, shield_icon
from app.core.enums import ResourceType


def shield(emoji_value: str | None):
    return SimpleNamespace(
        id=77,
        name="سپر تازه",
        emoji=emoji_value,
        purchase_resource=ResourceType.COIN,
        purchase_price=120,
        unlock_level=1,
        duration_minutes=30,
        daily_limit=None,
        description="محافظت کامل",
    )


def test_shield_custom_emoji_follows_item_across_views() -> None:
    item = shield("5917839500750364054")
    owned = SimpleNamespace(
        shield=item, active_until=datetime.now(UTC) + timedelta(minutes=25)
    )
    icon_link = "tg://emoji?id=5917839500750364054"

    assert icon_link in shield_icon(item)
    assert icon_link in _shield_catalog_banner(1, [owned], [item])
    assert icon_link in _shield_purchase_banner(item)
    assert icon_link in _shield_library_detail_text(item)
    assert (
        shield_catalog_keyboard([item], player_level=1)
        .inline_keyboard[0][0]
        .icon_custom_emoji_id
        == item.emoji
    )
    assert (
        shield_library_keyboard([item]).inline_keyboard[0][0].icon_custom_emoji_id
        == item.emoji
    )

    item.name = "سپر تغییرنام‌یافته"
    assert icon_link in _shield_purchase_banner(item)
    assert icon_link in _shield_library_detail_text(item)


def test_shield_accepts_regular_emoji_and_falls_back_when_empty() -> None:
    item = shield("🌈")
    assert shield_icon(item) == "🌈"
    assert shield_button_label(item) == "🌈 سپر تازه"
    button = shield_library_keyboard([item]).inline_keyboard[0][0]
    assert button.icon_custom_emoji_id is None
    assert button.text == "🌈 سپر تازه"

    item.emoji = None
    assert "tg://emoji?id=5825861861278490879" in shield_icon(item)
    assert shield_button_label(item) == "سپر تازه"


@pytest.mark.asyncio
async def test_admin_shield_create_stores_custom_emoji_id(monkeypatch) -> None:
    monkeypatch.setattr(admin_handlers, "allowed", lambda message: True)
    state_data = {
        "mode": "create",
        "name": "سپر تازه",
        "purchase_price": 120,
        "purchase_resource": ResourceType.COIN,
        "unlock_level": 1,
        "duration_minutes": 30,
        "daily_limit": None,
        "description": "محافظت کامل",
    }
    state = SimpleNamespace(
        get_data=AsyncMock(return_value=state_data),
        clear=AsyncMock(),
    )
    session = AsyncMock()
    create = AsyncMock(return_value=shield("5917839500750364054"))
    monkeypatch.setattr(admin_handlers.shield_service, "create_shield", create)
    message = SimpleNamespace(
        text="🌊",
        entities=[
            SimpleNamespace(type="custom_emoji", custom_emoji_id="5917839500750364054")
        ],
        answer=AsyncMock(),
    )

    await admin_handlers.s_emoji(message, state, session)

    assert create.await_args.kwargs["emoji"] == "5917839500750364054"
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_shield_edit_can_clear_emoji(monkeypatch) -> None:
    monkeypatch.setattr(admin_handlers, "allowed", lambda message: True)
    update = AsyncMock(return_value=shield(None))
    monkeypatch.setattr(admin_handlers.shield_service, "update_shield", update)
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"edit_field": "emoji", "edit_id": 77}),
        clear=AsyncMock(),
    )
    message = SimpleNamespace(text="-", entities=[], answer=AsyncMock())
    session = AsyncMock()

    await admin_handlers.shield_edit_value(message, state, session)

    update.assert_awaited_once_with(session, 77, emoji=None)
