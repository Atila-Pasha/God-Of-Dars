from types import SimpleNamespace

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
