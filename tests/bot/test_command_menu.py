from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from app.bot.commands import GROUP_COMMANDS, PRIVATE_COMMANDS, register_commands
from app.bot.keyboards.leaderboard import leaderboard_keyboard
from app.bot.middlewares.group import ALLOWED_GROUP_COMMANDS


def test_fighter_button_is_named_global() -> None:
    buttons = [
        button for row in leaderboard_keyboard().inline_keyboard for button in row
    ]
    assert any(button.text == "سراسری" for button in buttons)
    assert all(button.text != "مبارز" for button in buttons)


@pytest.mark.asyncio
async def test_telegram_command_menus_match_private_and_group_access() -> None:
    bot = SimpleNamespace(set_my_commands=AsyncMock())

    await register_commands(bot)

    private_call, group_call = bot.set_my_commands.await_args_list
    assert isinstance(private_call.kwargs["scope"], BotCommandScopeAllPrivateChats)
    assert isinstance(group_call.kwargs["scope"], BotCommandScopeAllGroupChats)
    assert private_call.kwargs["commands"] == list(PRIVATE_COMMANDS)
    assert group_call.kwargs["commands"] == list(GROUP_COMMANDS)
    assert {item.command for item in GROUP_COMMANDS} <= ALLOWED_GROUP_COMMANDS
    assert {"global", "rank", "leaderboard"} <= {
        item.command for item in PRIVATE_COMMANDS
    }
