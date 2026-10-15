from types import SimpleNamespace

from app.bot.banners import (
    archer_midway_banner,
    attack_preview_banner,
    attack_result_banner,
    castle_repair_reminder_banner,
    purchase_banner,
)
from app.bot.callbacks import CastleCallback
from app.bot.handlers.library import _teacher_detail_content
from app.bot.keyboards.school import castle_repair_reminder_keyboard
from app.services.attack_service import AttackPreview, AttackResult
from app.services.teacher_service import TeacherCapacity


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


def test_purchase_banner_shows_teacher_weight_and_after_purchase_capacity() -> None:
    teacher = SimpleNamespace(
        name="قضاتی",
        ability_text=None,
        emoji=None,
        purchase_resource=SimpleNamespace(value="COIN"),
        purchase_price=250,
        unlock_level=1,
        damage=100,
    )
    capacity = TeacherCapacity(owned=5, available=10, maximum=100, percent_based=True)

    full = purchase_banner(teacher, capacity=capacity, weight=9)
    assert "سهم این دبیر از ظرفیت" in full
    assert "9%" in full and "5% از 10%" in full
    assert "14% از 10%" in full
    assert "ظرفیت کافی نیست" in full
    assert "آیا خرید" not in full

    fitting = purchase_banner(teacher, capacity=capacity, weight=5)
    assert "10% از 10%" in fitting
    assert "آیا خرید" in fitting


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
    assert "کماندار" not in text
    assert "سهم احتمالی تیر" not in text


def test_midway_archer_message_has_ten_variants_and_teacher_icon() -> None:
    messages = {
        archer_midway_banner(index, "قضاتی", "123", "محسنی", "456", "تیر ساده", 6)
        for index in range(10)
    }
    assert len(messages) == 10
    assert all("6 HP" in message for message in messages)
    assert all("tg://emoji?id=123" in message for message in messages)
    assert all("tg://emoji?id=456" in message for message in messages)
    assert all("\\." in message for message in messages)


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
    assert "tg://emoji?id=5902520589356113908) موز: 1" in attacker
    assert "tg://emoji?id=5902520589356113908) موز: 0" in defender


def test_empty_target_bonus_is_visible_only_to_attacker_and_not_a_defender_loss() -> (
    None
):
    result = AttackResult(
        attack=SimpleNamespace(id=1),
        attacker_telegram_id=1,
        attacker_name="آرش",
        target_name="نگار",
        target_telegram_id=2,
        teacher_name="قضاتی",
        ability_text=None,
        castle_damage=20,
        teacher_injury=0,
        castle_strength_after=80,
        loot_coin=10,
        loot_diamond=0,
        loot_banana=20,
        bot_bonus_coin=10,
        castle_strength_before=100,
    )

    attacker = attack_result_banner(result)
    defender = attack_result_banner(result, recipient="defender")

    assert "حریف غنیمتی نداشت" in attacker
    assert "*10 سکه*" in attacker
    assert "طلا: 10" in attacker
    assert "طلا: 0" in defender
    assert "موز: 0" in defender
    assert "پاداش این حمله" not in defender


def test_destroyed_castle_report_calls_out_weak_attack() -> None:
    result = AttackResult(
        attack=SimpleNamespace(id=1),
        attacker_telegram_id=1,
        attacker_name="آرش",
        target_name="نگار",
        target_telegram_id=2,
        teacher_name="قضاتی",
        ability_text=None,
        castle_damage=0,
        teacher_injury=0,
        castle_strength_after=0,
        loot_coin=0,
        loot_diamond=0,
        loot_banana=0,
        castle_strength_before=0,
    )

    attacker = attack_result_banner(result)
    defender = attack_result_banner(result, recipient="defender")

    assert "میزان تخریب: *ضعیف کشی کردی*" in attacker
    assert "میزان تخریب: *0%*" not in attacker
    assert "از قبل کامل نابود شده بود" in attacker
    assert "دژت پیش از این حمله هم کامل نابود شده بود" in defender


def test_repair_reminder_has_premium_icon_and_repair_callback() -> None:
    banner = castle_repair_reminder_banner()
    button = castle_repair_reminder_keyboard().inline_keyboard[0][0]

    assert "tg://emoji?id=" in banner
    assert "فرمانده، دژت نیاز به تعمیر داره" in banner
    assert button.icon_custom_emoji_id == "5341715473882955310"
    assert CastleCallback.unpack(button.callback_data).action == "repair"


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
