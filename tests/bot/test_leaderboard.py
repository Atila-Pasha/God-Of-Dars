from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import GlobalRankCallback, LeaderboardCallback
from app.bot.handlers import leaderboard as leaderboard_handler
from app.bot.handlers.leaderboard import (
    GROUP_LEADERBOARD_PHRASES,
    global_rank_content,
    global_rank_markdown,
    leaderboard_content,
    leaderboard_markdown,
    leaderboard_text,
)
from app.bot.keyboards.leaderboard import global_rank_keyboard, leaderboard_keyboard
from app.bot.keyboards.profile import profile_keyboard
from app.services.leaderboard_service import FighterPage, LeaderboardEntry


def test_profile_keyboard_contains_private_leaderboard_button() -> None:
    keyboard = profile_keyboard(include_navigation=True, owner_id=42)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    leaderboard_button = next(
        button for button in buttons if button.text == "🏆 برترین‌ها"
    )

    assert LeaderboardCallback.unpack(leaderboard_button.callback_data).action == "menu"


def test_group_profile_keyboard_does_not_expose_leaderboard_button() -> None:
    keyboard = profile_keyboard(include_navigation=False, owner_id=42)

    assert all(
        button.text != "🏆 برترین‌ها"
        for row in keyboard.inline_keyboard
        for button in row
    )


def test_group_contract_contains_only_requested_leaderboard_categories() -> None:
    assert GROUP_LEADERBOARD_PHRASES["برترین فرمانده"] == (
        "commander",
        "weekly",
    )
    assert GROUP_LEADERBOARD_PHRASES["برترین دانش آموز روزانه"] == (
        "student",
        "daily",
    )
    assert GROUP_LEADERBOARD_PHRASES["برترین دانش آموزش هفتگی"] == (
        "student",
        "weekly",
    )
    assert GROUP_LEADERBOARD_PHRASES["برترین مبارز ماهانه"] == (
        "fighter",
        "monthly",
    )
    assert "برترین مبارز هفتگی" not in GROUP_LEADERBOARD_PHRASES


def test_fighter_board_renders_markdown_style_table_and_viewer_rank() -> None:
    entry = LeaderboardEntry(
        rank=1,
        user_id=7,
        name="علی رضایی",
        username="ali",
        primary_value=12,
        secondary_value=3456,
    )
    text = leaderboard_text(
        "fighter",
        (entry,),
        entry,
    )

    assert "رتبه" in text
    assert "اکانت" in text
    assert "🥇 1" in text
    assert "@ali" in text
    assert "12" in text
    assert "3,456" in text
    assert "#1 — @ali" in text

    entities = leaderboard_content("fighter", (entry,), entry).as_kwargs()["entities"]
    assert any(entity.type == "pre" for entity in entities)
    assert any(entity.type == "bold" for entity in entities)

    markdown = leaderboard_markdown("fighter", (entry,), entry, "monthly")
    assert markdown.startswith("# 🏆 Leaderboard")
    assert "| رتبه | اکانت | جام | برد |" in markdown
    assert "## ⚔️ برترین مبارزها — این ماه" in markdown


def test_leaderboard_keyboard_switches_category_and_period() -> None:
    keyboard = leaderboard_keyboard(active_kind="student", active_period="daily")
    callbacks = [
        LeaderboardCallback.unpack(button.callback_data)
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith("leaderboard:")
    ]

    assert any(
        item.action == "student" and item.period == "monthly" for item in callbacks
    )
    assert any(
        item.action == "fighter" and item.period == "daily" for item in callbacks
    )


def test_global_rank_banner_and_page_controls() -> None:
    entry = LeaderboardEntry(11, 7, "آرمان", "arman", 1801, 3)
    page = FighterPage(
        entries=(entry,),
        page=2,
        pages=3,
        total=23,
        updated_at=datetime(2026, 11, 6, 10, 0, tzinfo=UTC),
    )
    markdown = global_rank_markdown(page, entry)
    text = global_rank_content(page, entry).render()[0]
    keyboard = global_rank_keyboard(2, 3)
    pages = [
        GlobalRankCallback.unpack(button.callback_data).page
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "| # | مبارز | جام | رنک |" in markdown
    assert "tg://emoji?id=5915508067948051685" in markdown
    assert "دیاموندی" in markdown
    assert "1,801" in markdown
    assert "صفحه 2/3" in text
    assert "#11" in text
    assert "آخرین به‌روزرسانی: 2026/11/06، 13:30" in text
    assert any(
        entity.type == "custom_emoji"
        and entity.custom_emoji_id == "5915508067948051685"
        for entity in global_rank_content(page, entry).as_kwargs()["entities"]
    )
    assert pages == [1, 3, 2]
    assert [
        GlobalRankCallback.unpack(button.callback_data).page
        for row in global_rank_keyboard(1, 1).inline_keyboard
        for button in row
    ] == [1]


@pytest.mark.asyncio
async def test_group_fighter_phrase_opens_global_pages(monkeypatch) -> None:
    show_global = AsyncMock()
    monkeypatch.setattr(leaderboard_handler, "_show_global_rank", show_global)
    message = SimpleNamespace(text="برترین مبارز", answer=AsyncMock())
    session = SimpleNamespace()

    await leaderboard_handler.group_leaderboard_handler(message, session)

    show_global.assert_awaited_once_with(message, session)


@pytest.mark.asyncio
async def test_global_page_replies_in_group_with_navigation(monkeypatch) -> None:
    page = FighterPage(
        entries=(LeaderboardEntry(1, 7, "آرمان", "arman", 1801, 3),),
        page=1,
        pages=2,
        total=11,
    )
    monkeypatch.setattr(
        leaderboard_handler.leaderboards,
        "fighter_page",
        AsyncMock(return_value=page),
    )
    bot = SimpleNamespace(send_rich_message=AsyncMock())
    message = SimpleNamespace(
        from_user=None,
        chat=SimpleNamespace(id=-99, type="supergroup"),
        message_id=15,
        bot=bot,
        answer=AsyncMock(),
    )

    await leaderboard_handler._show_global_rank(message, SimpleNamespace())

    kwargs = bot.send_rich_message.await_args.kwargs
    assert kwargs["chat_id"] == -99
    assert kwargs["reply_parameters"].message_id == 15
    assert "tg://emoji?id=5915508067948051685" in kwargs["rich_message"].markdown
    assert (
        GlobalRankCallback.unpack(
            kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        ).page
        == 2
    )
