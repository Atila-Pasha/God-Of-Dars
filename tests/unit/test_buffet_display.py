from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import buffet
from app.bot.handlers.buffet import _resource_display, _resource_text
from app.bot.keyboards.buffet import buffet_keyboard
from app.core.enums import ResourceType
from app.core.game_logic import BuffetConversion


def test_buffet_conversion_buttons_show_only_resource_emojis() -> None:
    markup = buffet_keyboard(
        (
            BuffetConversion(
                source=ResourceType.DIAMOND,
                target=ResourceType.COIN,
                source_amount=10,
                target_amount=1,
            ),
        )
    )

    assert markup.inline_keyboard[0][0].text == "💎 ➜ 🪙"


def test_buffet_resource_messages_show_only_resource_emojis() -> None:
    assert _resource_display(ResourceType.DIAMOND) == "💎"
    assert _resource_display(ResourceType.COIN) == "🪙"
    assert _resource_text(SimpleNamespace(coin=12, diamond=3)) == "🪙: 12\n💎: 3"


@pytest.mark.asyncio
async def test_buffet_entry_keeps_all_menu_buttons(monkeypatch) -> None:
    monkeypatch.setattr(
        buffet.user_service, "get_active_by_telegram_user_id", AsyncMock()
    )
    message = SimpleNamespace(from_user=SimpleNamespace(id=42), answer=AsyncMock())

    await buffet.buffet_handler(message, AsyncMock())

    assert message.answer.await_count == 2
    for call in message.answer.await_args_list:
        keyboard = call.kwargs["reply_markup"]
        assert [row[0].text for row in keyboard.keyboard] == [
            "تبدیل منابع",
            "فهرست سپر ها",
            "خرید دبیر",
            "بازگشت به منو اصلی",
        ]
        assert all(row[0].icon_custom_emoji_id for row in keyboard.keyboard[:3])
