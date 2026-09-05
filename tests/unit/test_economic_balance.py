from app.core.enums import ResourceType
from app.core.game_logic import game_config


def test_mine_and_castle_progression_do_not_outgrow_high_level_income() -> None:
    for level in (1, 5, 10, 20, 50, 100, 200, 300, 400, 500):
        mine = game_config.mine_level(level)
        daily_diamonds = mine.diamond_per_minute * 1_440
        assert mine.diamond_cost is not None
        assert mine.diamond_cost <= max(1, daily_diamonds * 2, 13_000)

        castle_cost = game_config.castle_upgrade(level).diamond_cost
        assert castle_cost <= max(500, daily_diamonds * 4, 2_400)


def test_buffet_conversion_has_a_loss_and_cannot_create_resources() -> None:
    conversions = {
        (item.source, item.target): item for item in game_config.buffet_conversions
    }
    forward = conversions[(ResourceType.COIN, ResourceType.DIAMOND)]
    reverse = conversions[(ResourceType.DIAMOND, ResourceType.COIN)]
    returned_coins = (
        forward.target_amount
        * reverse.target_amount
        // reverse.source_amount
    )
    assert returned_coins < forward.source_amount


def test_upgrade_xp_reward_is_capped() -> None:
    for cost in (1, 100, 1_000, 1_000_000_000):
        assert (
            game_config.upgrade_banana_reward(cost)
            <= game_config.upgrade_banana_maximum
        )
