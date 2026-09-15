from app.bot.callbacks import LeaderboardCallback
from app.bot.handlers.leaderboard import GROUP_LEADERBOARD_PHRASES, leaderboard_text
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
    assert GROUP_LEADERBOARD_PHRASES["برترین فرمانده"] == "commander"
    assert GROUP_LEADERBOARD_PHRASES["برترین دانش آموز"] == "student"
    assert GROUP_LEADERBOARD_PHRASES["برترین دانش آموزش"] == "student"
    assert GROUP_LEADERBOARD_PHRASES["برترین مبارز"] == "fighter"


def test_fighter_board_renders_farsi_numbers_and_username() -> None:
    text = leaderboard_text(
        "fighter",
        (
            LeaderboardEntry(
                rank=1,
                user_id=7,
                name="علی رضایی",
                username="ali",
                primary_value=12,
                secondary_value=3456,
            ),
        ),
    )

    assert "🥇 علی رضایی (@ali)" in text
    assert "۱۲ پیروزی" in text
    assert "۳٬۴۵۶ آسیب" not in text
    assert "۳,۴۵۶ آسیب" in text
