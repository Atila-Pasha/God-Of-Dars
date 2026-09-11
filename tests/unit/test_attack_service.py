from types import SimpleNamespace

import pytest

from app.bot.utils.attack import teacher_phrase
from app.core.enums import ResourceType
from app.core.game_logic import AttackRules, CastleRepairRules, GameConfig
from app.services.attack_service import AttackService


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("افلاطون", "دبیر افلاطون"),
        ("افلاطون، ارسطو", "دبیر های افلاطون ارسطو"),
        ("افلاطون، ارسطو، نیوتن", "دبیر های افلاطون ارسطو نیوتن"),
    ],
)
def test_teacher_phrase_matches_attack_teacher_count(names, expected):
    assert teacher_phrase(names) == expected


class _ClaimSession:
    def __init__(self, rowcounts: list[int]) -> None:
        self.rowcounts = iter(rowcounts)

    async def execute(self, statement):
        return SimpleNamespace(rowcount=next(self.rowcounts))


@pytest.mark.asyncio
@pytest.mark.parametrize("record_ids", [(1,), (1, 2), (1, 2, 3, 4)])
async def test_attack_xp_claim_is_one_time_for_any_command_size(record_ids):
    session = _ClaimSession([1, *([0] * (len(record_ids) - 1))])

    claims = [
        await AttackService._claim_attack_xp(
            session, attack_command_id="command-100", attack_id=record_id
        )
        for record_id in record_ids
    ]

    assert claims.count(True) == 1


def test_loot_is_capped_by_teacher_power_not_target_wealth():
    config = GameConfig(
        attack_rules=AttackRules(
            loot_percent=50,
            loot_coin_per_power=10,
            loot_diamond_per_power=0.1,
        ),
        castle_repair=CastleRepairRules(
            loot_bonus_percent_at_zero_strength=0,
            maximum_loot_percent=100,
        ),
    )
    service = AttackService(config=config)
    modest_target = SimpleNamespace(
        resources=SimpleNamespace(coin=200, diamond=20, banana=0)
    )
    rich_target = SimpleNamespace(
        resources=SimpleNamespace(coin=2_000_000, diamond=200_000, banana=0)
    )

    modest_loot = service._loot(
        modest_target, castle_damage=100, castle_strength=100, attack_power=10
    )
    rich_loot = service._loot(
        rich_target, castle_damage=100, castle_strength=100, attack_power=10
    )

    assert modest_loot["loot_coin"] == rich_loot["loot_coin"] == 100
    assert modest_loot["loot_diamond"] == rich_loot["loot_diamond"] == 1


def test_stronger_teacher_has_a_larger_but_still_bounded_loot_capacity():
    rules = AttackRules(
        loot_coin_per_power=10,
        loot_diamond_per_power=0.1,
    )

    assert rules.loot_cap(10, ResourceType.COIN) == 100
    assert rules.loot_cap(25, ResourceType.COIN) == 250
