from types import SimpleNamespace

from app.bot.banners import attack_preview_banner, attack_result_banner, purchase_banner
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
    assert "tg://emoji?id=123)قضاتی \\- ![" in attacker
    assert "tg://emoji?id=456)فراهانی" in attacker
    assert "حمله به قلعه" in attacker
    assert "به قلعهٔ تو" in defender
    assert "دفاعت را تقویت کن" in defender
    assert "منابع ازدست‌رفته" in defender
    assert "> 80 DMG" in attacker
    assert "> 20 DMG" in defender
