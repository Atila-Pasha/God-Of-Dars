from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.banners import attack_result_banner, attack_teacher_injury_banner
from app.core.enums import AttackStatus
from app.services.attack_service import AttackResult
from app.workers.attack_resolver import _command_result


def _attack_row(
    attack_id: int,
    name: str,
    damage: int,
    injury: int,
    *,
    status: AttackStatus = AttackStatus.RESOLVED,
    remaining_hp: int | None = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=attack_id,
        status=status,
        teacher=(
            SimpleNamespace(current_hp=remaining_hp)
            if remaining_hp is not None
            else None
        ),
        teacher_name_snapshot=name,
        teacher_ability_snapshot=f"توانایی {name}",
        teacher_emoji_snapshot=str(attack_id),
        result_damage=damage,
        result_raid_damage=0,
        result_teacher_injury=injury,
        loot_coin=damage,
        loot_diamond=1,
        loot_banana=0,
        bot_bonus_coin=0,
        mine_loot_coin=0,
        mine_loot_diamond=0,
        target_castle_strength_snapshot=100,
        source_chat_id=-100123,
    )


@pytest.mark.asyncio
async def test_report_waits_for_every_teacher_then_sums_the_command() -> None:
    rows = [
        _attack_row(1, "قضاتی", 30, 2),
        _attack_row(
            2,
            "فراهانی",
            40,
            3,
            status=AttackStatus.PROCESSING,
            remaining_hp=None,
        ),
    ]
    session = SimpleNamespace(scalars=AsyncMock(return_value=rows))
    result = AttackResult(
        attack=SimpleNamespace(attack_command_id="command-1"),
        attacker_telegram_id=10,
        attacker_name="آرش",
        target_name="نگار",
        target_telegram_id=20,
        teacher_name="فراهانی",
        ability_text=None,
        castle_damage=40,
        teacher_injury=3,
        castle_strength_after=30,
        loot_coin=40,
        loot_diamond=1,
        loot_banana=0,
    )

    assert await _command_result(session, result) is None

    rows[1].status = AttackStatus.RESOLVED
    summary = await _command_result(session, result)

    assert summary.castle_damage == 70
    assert summary.teacher_injury == 5
    assert summary.loot_coin == 70
    assert len(summary.teacher_details) == 2
    assert summary.source_chat_id == -100123
    assert summary.teacher_injuries[0].damage == 2
    assert summary.teacher_injuries[0].remaining_hp == 20
    assert not summary.teacher_injuries[0].lost
    assert summary.teacher_injuries[1].damage == 3
    assert summary.teacher_injuries[1].lost
    banner = attack_teacher_injury_banner(summary)
    assert "2 HP" in banner
    assert "3 HP" in banner
    assert "جان باقی‌مانده" in banner
    assert "> 《 جان باقی‌مانده: *20 HP* 》" in banner
    assert "Let’s go to the hospital\\." in banner
    assert "دبیرت را در نبرد از دست دادی" in banner


def test_archer_hit_names_both_combatants_and_arrow_pack() -> None:
    result = AttackResult(
        attack=SimpleNamespace(),
        attacker_telegram_id=10,
        attacker_name="آرش",
        target_name="نگار",
        target_telegram_id=20,
        teacher_name="فراهانی",
        ability_text=None,
        castle_damage=10,
        teacher_injury=12,
        castle_strength_after=90,
        loot_coin=0,
        loot_diamond=0,
        loot_banana=0,
        archer_hits=(("فراهانی", "123", "محسنی", "تیر ساده", "456", 6),),
    )

    report = attack_result_banner(result)
    assert "کماندار محسنی" in report
    assert "تیر ساده" in report
    assert "فراهانی" in report
    assert "6 HP" in report
    assert "tg://emoji?id=123" in report
    assert "tg://emoji?id=456" in report
