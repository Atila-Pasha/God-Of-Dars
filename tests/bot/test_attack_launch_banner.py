from app.bot.banners import attack_launch_banner, rich_plain
from app.bot.callbacks import AttackCountdownCallback
from app.bot.handlers.battle import _attack_countdown_keyboard


def test_launch_banner_renders_teacher_icons_and_real_remaining_time() -> None:
    teachers = (("قضاتی", None, "123"), ("فراهانی", None, "456"))

    starting = attack_launch_banner("حریف [قوی]", teachers)
    updated = attack_launch_banner("حریف [قوی]", teachers, remaining_seconds=92)

    assert "حریف \\[قوی\\]" in starting
    assert "دبیر :\n" in starting
    assert "tg://emoji?id=123)قضاتی \\- ![" in starting
    assert "tg://emoji?id=456)فراهانی" in starting
    assert "پس از پایان زمان" in starting
    assert "زمان باقی‌مانده تا تکمیل حمله: 01:32" in updated
    assert "پس از پایان زمان" not in updated


def test_countdown_button_carries_command_id_and_custom_icon() -> None:
    command_id = "12345678-1234-1234-1234-123456789abc"
    button = _attack_countdown_keyboard(command_id).inline_keyboard[0][0]

    assert button.icon_custom_emoji_id == "5825746176334373354"
    assert AttackCountdownCallback.unpack(button.callback_data).command_id == command_id


def test_rich_plain_escapes_text_and_preserves_custom_emoji() -> None:
    content = rich_plain("📚 درس [یک].")
    assert "tg://emoji?id=5825629907274703191" in content
    assert "\\[یک\\]\\." in content
