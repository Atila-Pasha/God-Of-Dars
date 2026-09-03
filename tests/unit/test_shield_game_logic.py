from app.core.game_logic import GameConfig, GameConfigurationError, ShieldRules


def test_shield_reduces_percent_and_flat_damage_without_going_below_zero() -> None:
    config = GameConfig(
        shield_rules=ShieldRules(max_flat_absorption=100),
    )

    result = config.apply_shield(
        100,
        reduction_percent=25,
        flat_absorption=15,
    )

    assert result.incoming_damage == 100
    assert result.blocked_damage == 40
    assert result.remaining_damage == 60
    assert config.apply_shield(
        10, reduction_percent=100, flat_absorption=100
    ).remaining_damage == 0


def test_shield_values_are_limited_by_toml_rules() -> None:
    config = GameConfig(shield_rules=ShieldRules(max_flat_absorption=20))

    try:
        config.apply_shield(100, reduction_percent=10, flat_absorption=21)
    except GameConfigurationError:
        pass
    else:
        raise AssertionError("invalid shield absorption should be rejected")
