from app.bot.callbacks import LeaderboardCallback
from app.bot.handlers.leaderboard import (
    GROUP_LEADERBOARD_PHRASES,
    leaderboard_content,
    leaderboard_markdown,
    leaderboard_text,
)
from app.bot.keyboards.leaderboard import leaderboard_keyboard
from app.bot.keyboards.profile import profile_keyboard
from app.services.leaderboard_service import LeaderboardEntry


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
    assert "🥇 ۱" in text
    assert "@ali" in text
    assert "۱۲" in text
    assert "۳,۴۵۶" in text
    assert "#۱ — @ali" in text

    entities = leaderboard_content("fighter", (entry,), entry).as_kwargs()["entities"]
    assert any(entity.type == "pre" for entity in entities)
    assert any(entity.type == "bold" for entity in entities)

    markdown = leaderboard_markdown("fighter", (entry,), entry, "monthly")
    assert markdown.startswith("# 🏆 Leaderboard")
    assert "| رتبه | اکانت | برد | آسیب |" in markdown
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
