from dataclasses import dataclass

from admin import keyboards
from admin.handlers import button_labels
from app.bot.custom_emojis import _decorate_markup


def labels(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def inline_data(markup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_main_menu_is_a_small_section_dashboard() -> None:
    markup = keyboards.main()

    assert labels(markup) == [
        "👥 کاربران و گزارش‌ها",
        "🎮 محتوای بازی",
        "📤 ارسال و جایزه",
        "⚙️ تنظیمات ربات",
    ]
    assert markup.resize_keyboard is True
    assert markup.is_persistent is True


def test_main_routes_accept_text_returned_by_premium_icon_buttons() -> None:
    markup = keyboards.main()
    source_labels = labels(markup)

    _decorate_markup({"reply_markup": markup})

    for source, telegram_text in zip(source_labels, labels(markup), strict=True):
        assert telegram_text in button_labels(source)


def test_each_section_has_a_direct_home_action() -> None:
    menus = (
        keyboards.users_menu(),
        keyboards.content_menu(),
        keyboards.publishing_menu(),
        keyboards.settings_menu(),
    )

    for markup in menus:
        assert "🏠 منوی اصلی" in labels(markup)


def test_content_menu_exposes_create_actions_without_commands() -> None:
    content_labels = labels(keyboards.content_menu())

    assert "➕ دبیر جدید" in content_labels
    assert "➕ سپر جدید" in content_labels
    assert "➕ پک مطالعه جدید" in content_labels


@dataclass
class Channel:
    id: int
    username: str | None
    telegram_id: int | None


def test_channel_actions_are_button_driven() -> None:
    markup = keyboards.channel_actions(
        [Channel(id=7, username="godofdars", telegram_id=None)]
    )

    assert inline_data(markup) == [
        "admin_channel:add",
        "admin_channel:delete:7",
        "admin_channel:clear_confirm",
    ]
