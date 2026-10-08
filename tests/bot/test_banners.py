from types import SimpleNamespace

from app.bot.banners import attack_preview_banner, attack_result_banner, purchase_banner
from app.bot.handlers.library import _teacher_detail_content
from app.services.attack_service import AttackPreview, AttackResult


def test_purchase_banner_escapes_teacher_data_and_uses_custom_emoji() -> None:
    teacher = SimpleNamespace(
        name="قضاتی [آزمایشی]",
        ability_text="ملخک‌ها `قوی`",
        emoji="123456789",
        purchase_resource=SimpleNamespace(value="COIN"),
        purchase_price=250,
        unlock_level=3,
    )

    text = purchase_banner(teacher)

    assert "tg://emoji?id=123456789" in text
    assert "*قضاتی \\[آزمایشی\\]*" in text
    assert "ملخک‌ها \\`قوی\\`" in text
    assert "سطح بازشدن: 3" in text
    assert "> سطح بازشدن: 3" in text


def test_attack_preview_lists_teachers_without_icon_gap_or_summary() -> None:
    preview = AttackPreview(
        attacker_id=1,
        target_id=2,
        teacher_id=3,
        attacker_name="آرش",
        target_name="نگار",
        teacher_name="قضاتی، فراهانی",
        ability_text=None,
        teacher_damage=80,
        defense_power=50,
        estimated_castle_damage=30,
        estimated_teacher_injury=7,
        loot_coin=10,
        loot_diamond=2,
        loot_banana=1,
        teacher_details=(
            ("قضاتی", "لشکر ملخک‌ها", "123"),
            ("فراهانی", "سپاه کتاب‌ها", "456"),
        ),
    )

    text = attack_preview_banner(preview)

    assert "tg://emoji?id=123)*قضاتی*" in text
    assert "tg://emoji?id=456)*فراهانی*" in text
    assert "نیروهای تنظیم‌شده:\n\n" in text
    assert "قضاتی + فراهانی" not in text
    assert "الماس" not in text
    assert "> 50 DMG" in text
    assert "tg://emoji?id=5825699971076202989) *طلا*: 10" in text
    assert "tg://emoji?id=5902520589356113908) *موز*: 1" in text


def test_attack_report_differs_for_defender_and_uses_total_damage() -> None:
    result = AttackResult(
        attack=SimpleNamespace(id=1),
        attacker_telegram_id=1,
        attacker_name="آرش",
        target_name="نگار",
        target_telegram_id=2,
        teacher_name="قضاتی، فراهانی",
        ability_text=None,
        castle_damage=80,
        teacher_injury=7,
        castle_strength_after=20,
        loot_coin=10,
        loot_diamond=2,
        loot_banana=1,
        castle_strength_before=100,
        teacher_details=(("قضاتی", None, "123"), ("فراهانی", None, "456")),
    )

    attacker = attack_result_banner(result)
    defender = attack_result_banner(result, recipient="defender")

    assert "80%" in attacker
    assert "tg://emoji?id=123" in attacker
    assert "tg://emoji?id=456" in attacker
    assert "《![" in attacker
    assert "tg://emoji?id=123) قضاتی》  《![" in attacker
    assert "tg://emoji?id=456) فراهانی》" in attacker
    assert "حمله به قلعه" in attacker
    assert "به قلعهٔ تو" in defender
    assert "دفاعت را تقویت کن" in defender
    assert "منابع ازدست‌رفته" in defender
    assert "> 80 DMG" in attacker
    assert "> 20 DMG" in defender
    for banner in (attacker, defender):
        assert "tg://emoji?id=5825699971076202989) طلا: 10" in banner
        assert "tg://emoji?id=5825753314570018832) الماس: 2" in banner
        assert "tg://emoji?id=5902520589356113908) موز: 1" in banner


def test_teacher_introduction_uses_custom_icons_and_quoted_description() -> None:
    teacher = SimpleNamespace(
        name="پارسا فراهانی",
        emoji="123456789",
        damage=362,
        max_hp=675,
        purchase_price=440000,
        purchase_resource=SimpleNamespace(value="COIN"),
        upgrade_price=1420,
        unlock_level=17,
        ability_text="حملهٔ تف‌تفی مرگبار",
        description="پرتاب حباب‌های سمی.\nنگهبان را تضعیف می‌کند.",
    )

    text = _teacher_detail_content(teacher)

    assert r"*پروندهٔ دبیر \| پارسا فراهانی*" in text
    for icon_id in (
        "5825822115651133329",
        "5213455977919039650",
        "5825699971076202989",
        "5825753314570018832",
        "5825727141039317043",
        "5825647731388981287",
        "5825627287344651886",
    ):
        assert f"tg://emoji?id={icon_id}" in text
    assert "> پرتاب حباب‌های سمی\\.\n> نگهبان را تضعیف می‌کند\\." in text
