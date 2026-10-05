from types import SimpleNamespace

from app.bot.handlers.mine import _mine_text, _ore_bar
from app.services.shield_service import ShieldService


def test_mine_bar_uses_premium_emoji_in_visual_left_to_right_order() -> None:
    empty = _ore_bar(0, 2000)
    half = _ore_bar(1000, 2000)
    full = _ore_bar(2000, 2000)

    assert empty.startswith("\u2066![▫️](tg://emoji?id=5931534188657254206)")
    assert "tg://emoji?id=5931275038920548077" in empty
    assert half.count("tg://emoji?id=5933785859621920322") == 3
    assert "tg://emoji?id=5947346029153100052" in half
    assert "tg://emoji?id=5949744124142820550" in full
    assert _ore_bar(2100, 2000) == full
    assert all(
        bar.startswith("\u2066") and "\u2069" in bar for bar in (empty, half, full)
    )


def test_mine_banner_uses_actual_production_scale() -> None:
    snapshot = SimpleNamespace(
        level=2,
        production=SimpleNamespace(coin_per_minute=4, diamond_per_minute=1),
        collected_minutes=12,
        today_coin=1035,
        today_diamond=450,
        daily_produced_minutes=360,
    )
    text = _mine_text(snapshot)

    assert "1,035" in text
    assert "450" in text
    assert "1,440 / 2,880" in text
    assert "360 / 720" in text
    assert "tg://emoji?id=594" in text


def test_diamond_without_production_has_no_fake_capacity() -> None:
    snapshot = SimpleNamespace(
        level=1,
        production=SimpleNamespace(coin_per_minute=2, diamond_per_minute=0),
        collected_minutes=12,
        today_coin=1530,
        today_diamond=0,
        daily_produced_minutes=720,
    )
    text = _mine_text(snapshot)

    assert "تولید الماس در این سطح هنوز فعال نیست" in text
    assert "موجودی قابل برداشت: *\u20660\u2069*" in text
    assert "1,530" in text
    assert "1,440 / 1,440" in text
    assert "\u2066100%\u2069" in text


def test_kazemi_shield_exception_only_applies_to_named_teachers() -> None:
    kazemi = SimpleNamespace(name="سپر کاظمی")
    stronger = SimpleNamespace(name="سپر خسروپناه")

    assert ShieldService._kazemi_bypassed(kazemi, ("موسوی",))
    assert ShieldService._kazemi_bypassed(kazemi, ("کاظم قلمچی",))
    assert not ShieldService._kazemi_bypassed(kazemi, ("قضاتی",))
    assert not ShieldService._kazemi_bypassed(stronger, ("موسوی",))
