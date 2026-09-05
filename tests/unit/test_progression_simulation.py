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
        assert game_config.castle_max_strength(level) >= game_config.initial_castle_strength
        assert game_config.castle_upgrade(level).diamond_cost > 0

        if level < game_config.level_progression.max_level:
            cost = game_config.level_progression.upgrade_cost(level)
            assert cost is not None and cost > 0
            cost_values.append(cost)

    assert xp_values == sorted(xp_values)
    assert cost_values == sorted(cost_values)
    assert game_config.teacher_slots(500) == game_config.max_owned_teacher_slots


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
