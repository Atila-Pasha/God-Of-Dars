from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import buffet
from app.bot.handlers.buffet import (
    _resource_display,
    _resource_text,
    _shield_catalog_banner,
)
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

    assert markup.inline_keyboard[0][0].text == "تبدیل الماس به طلا"
    assert markup.inline_keyboard[0][0].icon_custom_emoji_id is None


def test_buffet_resource_messages_show_only_resource_emojis() -> None:
    assert _resource_display(ResourceType.DIAMOND) == "💎"
    assert _resource_display(ResourceType.COIN) == "🪙"
    text = _resource_text(SimpleNamespace(coin=12, diamond=3))
    assert "طلا: 12" in text and "الماس: 3" in text
    assert "tg://emoji?id=5823329527085931340" in text


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
        assert [row[0].icon_custom_emoji_id for row in keyboard.keyboard] == [
            "5220021677244559322",
            "5825861861278490879",
            "5784897390922174736",
            "5235864325540815679",
        ]


def test_shield_catalog_banner_uses_rich_text_and_escapes_descriptions() -> None:
    shield = SimpleNamespace(
        name="سپر [طلایی]",
        purchase_resource=ResourceType.COIN,
        purchase_price=150,
        duration_minutes=45,
        unlock_level=3,
        description="حفاظت ویژه [قوی]",
    )

    text = _shield_catalog_banner(3, [], [shield])

    assert "tg://emoji?id=5825861861278490879" in text
    assert "*سپر \\[طلایی\\]*" in text
    assert "حفاظت ویژه \\[قوی\\]" in text
    assert "150" in text
    assert "45 دقیقه" in text


def test_shield_banner_shows_daily_limits_and_supplied_emoji_ids() -> None:
    shields = [
        SimpleNamespace(
            name=name,
            purchase_resource=resource,
            purchase_price=price,
            duration_minutes=minutes,
            unlock_level=level,
            daily_limit=2 if level == 1 else 1,
            description="محافظت کامل",
        )
        for name, resource, price, minutes, level in (
            ("سپر زنگ تفریح", ResourceType.COIN, 120, 30, 1),
            ("سپر آلودگی هوا", ResourceType.DIAMOND, 1000, 180, 5),
        )
    ]

    text = _shield_catalog_banner(500, [], shields)

    assert "فقط 2 بار" in text
    assert "فقط 1 بار" in text
    for emoji_id in (
        "5915888842568638290",
        "5825727141039317043",
        "5825898080737697438",
        "5825861861278490879",
        "5825699971076202989",
        "6039539366177541657",
        "5825699618888884083",
        "5427240268589968037",
        "5917839500750364054",
        "5825753314570018832",
        "5823388325188214894",
    ):
        assert f"tg://emoji?id={emoji_id}" in text
