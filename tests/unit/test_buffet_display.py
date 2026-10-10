from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import buffet
from app.bot.handlers.buffet import (
    _conversion_prompt_banner,
    _conversion_success_banner,
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


@pytest.mark.parametrize(
    ("source", "target", "source_amount", "target_amount", "title"),
    [
        (ResourceType.COIN, ResourceType.DIAMOND, 100, 1, "طلا به الماس"),
        (ResourceType.DIAMOND, ResourceType.COIN, 1, 100, "الماس به طلا"),
    ],
)
def test_conversion_prompt_has_rich_rate_and_clear_input(
    source, target, source_amount, target_amount, title
) -> None:
    option = BuffetConversion(
        source=source,
        target=target,
        source_amount=source_amount,
        target_amount=target_amount,
    )

    text = _conversion_prompt_banner(source, target, option)

    assert f"*تبدیل {title}*" in text
    assert f"*نمونه:* {source_amount}" in text
    assert f"مضربی از {source_amount}" in text
    assert text.count("tg://emoji?id=") == 4


def test_conversion_success_renders_balances_as_markdown_custom_emoji() -> None:
    text = _conversion_success_banner(
        ResourceType.COIN,
        ResourceType.DIAMOND,
        100,
        1,
        SimpleNamespace(coin=1_000_000_351, diamond=20),
    )

    assert "*تبدیل با موفقیت انجام شد*" in text
    assert "*مصرف‌شده:* 100 ![🪙](tg://emoji?id=5823329527085931340)" in text
    assert "*دریافت‌شده:* 1 ![💎](tg://emoji?id=5825753314570018832)" in text
    assert "طلا: 1,000,000,351" in text
    assert "الماس: 20" in text


@pytest.mark.asyncio
async def test_conversion_messages_use_markdown_v2(monkeypatch) -> None:
    monkeypatch.setattr(buffet, "Message", SimpleNamespace)
    monkeypatch.setattr(
        buffet.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=12)),
    )
    monkeypatch.setattr(
        buffet.buffet_service,
        "resources",
        AsyncMock(return_value=SimpleNamespace(coin=900, diamond=1)),
    )
    exchange = AsyncMock(
        return_value=SimpleNamespace(
            packages=1,
            conversion=SimpleNamespace(target_amount=1),
        )
    )
    monkeypatch.setattr(buffet.buffet_service, "exchange", exchange)
    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(),
        get_data=AsyncMock(return_value={"source": "COIN", "target": "DIAMOND"}),
        clear=AsyncMock(),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        text="100",
        answer=AsyncMock(),
    )
    callback = SimpleNamespace(
        from_user=message.from_user,
        message=message,
        answer=AsyncMock(),
    )

    await buffet.buffet_callback(
        callback,
        SimpleNamespace(source="COIN", target="DIAMOND"),
        AsyncMock(),
        state,
    )
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"

    await buffet.buffet_exchange_message(message, state, AsyncMock())
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"
    assert "tg://emoji?id=5825753314570018832" in message.answer.await_args.args[0]


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
    assert "> *اثر:* جلوگیری کامل از حمله\n> حفاظت ویژه \\[قوی\\]" in text
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
            emoji=(
                "5825861861278490879"
                if name == "سپر زنگ تفریح"
                else "5917839500750364054"
            ),
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
