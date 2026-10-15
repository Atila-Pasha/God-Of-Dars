from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.archers import show_menu
from app.bot.keyboards.school import school_archers_keyboard


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
