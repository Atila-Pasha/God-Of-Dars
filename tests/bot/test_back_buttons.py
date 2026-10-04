from admin.keyboards import users_menu
from app.bot.custom_emojis import _decorate_markup, premium_emoji_id
from app.bot.keyboards.buffet import buffet_menu_keyboard, shield_inventory_keyboard
from app.bot.keyboards.daily import daily_keyboard
from app.bot.keyboards.leaderboard import leaderboard_keyboard
from app.bot.keyboards.library import study_keyboard
from app.bot.keyboards.main_menu import section_back_keyboard
from app.bot.keyboards.school import castle_keyboard, school_navigation_keyboard


def test_all_back_buttons_use_requested_premium_icon() -> None:
    assert premium_emoji_id("🔙") == "5235864325540815679"
    markups = [
        section_back_keyboard(),
        school_navigation_keyboard(),
        castle_keyboard(can_upgrade=False),
        buffet_menu_keyboard(),
        shield_inventory_keyboard([]),
        study_keyboard([]),
        leaderboard_keyboard(),
        daily_keyboard([]),
        users_menu(),
    ]
    for markup in markups:
        _decorate_markup({"reply_markup": markup})
        rows = getattr(markup, "inline_keyboard", None) or markup.keyboard
        back_buttons = [
            button
            for row in rows
            for button in row
            if "بازگشت" in button.text
            or "مدرسه من" in button.text
            or "بوفه" in button.text
            or "کتابخانه" in button.text
            or "منوی اصلی" in button.text
        ]
        assert back_buttons
        assert all(
            button.icon_custom_emoji_id == "5235864325540815679"
            for button in back_buttons
        )
