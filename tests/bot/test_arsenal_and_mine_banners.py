from types import SimpleNamespace

from app.bot.handlers.mine import _mine_text, _ore_bar
from app.services.shield_service import ShieldService


def test_mine_bar_moves_with_the_uncollected_amount() -> None:
    empty = _ore_bar(0, 2000)
    half = _ore_bar(1000, 2000)
    full = _ore_bar(2000, 2000)

    assert empty.count("tg://emoji?id=") == 8
    assert half.count("tg://emoji?id=") == 8
    assert full.count("tg://emoji?id=") == 8
    assert empty.count("![🟩]") == 0
    assert half.count("![🟩]") == 4
    assert full.count("![🟩]") == 8


def test_mine_banner_uses_actual_production_scale() -> None:
    snapshot = SimpleNamespace(
        level=2,
        production=SimpleNamespace(coin_per_minute=4, diamond_per_minute=1),
        collected_minutes=12,
        today_coin=1035,
        today_diamond=450,
    )
    text = _mine_text(snapshot)

    assert "1,035 / 2,880" in text
    assert "450 / 720" in text
    assert text.count("tg://emoji?id=594") > 0


def test_kazemi_shield_exception_only_applies_to_named_teachers() -> None:
    kazemi = SimpleNamespace(name="سپر کاظمی")
    stronger = SimpleNamespace(name="سپر خسروپناه")

    assert ShieldService._kazemi_bypassed(kazemi, ("موسوی",))
    assert ShieldService._kazemi_bypassed(kazemi, ("کاظم قلمچی",))
    assert not ShieldService._kazemi_bypassed(kazemi, ("قضاتی",))
    assert not ShieldService._kazemi_bypassed(stronger, ("موسوی",))
