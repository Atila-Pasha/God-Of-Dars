from app.core.enums import ResourceType
from app.core.game_logic import game_config


def test_progression_is_defined_and_bounded_through_level_500() -> None:
    checkpoints = (1, 5, 10, 20, 50, 100, 200, 300, 500)
    xp_values = []
    cost_values = []

    for level in checkpoints:
        xp = game_config.level_progression.required_xp(level)
        if level < game_config.level_progression.max_level:
            assert xp is not None and xp > 0
            xp_values.append(xp)
        assert game_config.teacher_slots(level) >= 1
        mine = game_config.mine_level(level)
        assert mine.coin_per_minute >= 0
        assert mine.diamond_per_minute >= 0
        assert mine.diamond_cost > 0
        assert (
            game_config.castle_max_strength(level)
            >= game_config.initial_castle_strength
        )
        assert game_config.castle_upgrade(level).diamond_cost > 0

        if level < game_config.level_progression.max_level:
            cost = game_config.level_progression.upgrade_cost(level)
            assert cost is not None and cost > 0
            cost_values.append(cost)

    assert xp_values == sorted(xp_values)
    assert cost_values == sorted(cost_values)
    assert game_config.teacher_slots(500) == game_config.max_owned_teacher_slots


def test_level_upgrade_uses_the_authoritative_xp_curve_and_keeps_overflow() -> None:
    for level in (1, 10, 15, 29, 100):
        assert game_config.level_progression.upgrade_cost(level) == (
            game_config.level_progression.required_xp(level)
        )
    assert game_config.level_progression.reset_xp_on_level_up is False


def test_first_diamond_mine_level_is_reachable_before_passive_income() -> None:
    assert game_config.mine_level(1).diamond_per_minute == 0
    assert game_config.mine_level(2).diamond_cost == 120


def test_diamond_teacher_sale_refunds_equivalent_coin_value() -> None:
    assert (
        game_config.teacher_sell_price(
            999_999,
            purchase_price=1_000,
            purchase_resource=ResourceType.DIAMOND,
        )
        == 45_000
    )


def test_teacher_damage_has_a_configured_high_level_cap() -> None:
    base_damage = 100
    for level in (1, 10, 50, 100, 500):
        damage = game_config.teacher_damage(1, level, base_damage)
        assert 0 < damage <= base_damage * game_config.teacher_damage_max_multiplier


def test_ownership_capacity_is_separate_from_attack_capacity() -> None:
    expected = {
        1: 1,
        5: 2,
        10: 4,
        20: 6,
        50: 10,
        100: 15,
        200: 20,
        500: 30,
    }
    for level, capacity in expected.items():
        assert game_config.teacher_slots(level) == capacity
    assert game_config.max_attack_teachers == 4


def test_upgrade_banana_reward_scales_with_diamond_cost() -> None:
    assert game_config.upgrade_banana_reward(100) == 10
    assert game_config.upgrade_banana_reward(500) == 50
    assert game_config.upgrade_banana_reward(10_000) == 500


def test_teacher_upgrade_cost_grows_for_each_level_transition() -> None:
    costs = [game_config.teacher_upgrade_cost(1_000, level) for level in range(1, 21)]

    assert costs[0] == 1_000
    assert costs[1] == 1_195
    assert costs[2] == 1_420
    assert costs == sorted(costs)
    assert len(costs) == len(set(costs))


def test_small_teacher_base_price_still_changes_at_every_level() -> None:
    costs = [game_config.teacher_upgrade_cost(1, level) for level in range(1, 8)]

    assert costs[0] == 1
    assert all(after > before for before, after in zip(costs, costs[1:], strict=False))
