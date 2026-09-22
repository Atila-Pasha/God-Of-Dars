from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ResourceType
from app.core.game_logic import GameConfig, GameConfigurationError, ShieldRules
from app.models.shield import Shield
from app.models.user_shield import UserShield
from app.services.shield_service import ShieldService


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
    assert (
        config.apply_shield(
            10, reduction_percent=100, flat_absorption=100
        ).remaining_damage
        == 0
    )


def test_shield_values_are_limited_by_toml_rules() -> None:
    config = GameConfig(shield_rules=ShieldRules(max_flat_absorption=20))

    try:
        config.apply_shield(100, reduction_percent=10, flat_absorption=21)
    except GameConfigurationError:
        pass
    else:
        raise AssertionError("invalid shield absorption should be rejected")


@pytest.mark.asyncio
async def test_active_timed_shield_blocks_the_entire_attack() -> None:
    shield = Shield(
        id=4,
        name="آزمایشی",
        reduction_percent=25,
        flat_absorption=15,
        purchase_price=100,
        purchase_resource=ResourceType.COIN,
        unlock_level=1,
        duration_minutes=60,
        is_active=True,
    )
    active = UserShield(
        id=8,
        user_id=2,
        shield_id=shield.id,
        quantity=1,
        is_equipped=True,
        active_until=datetime.now(UTC) + timedelta(minutes=30),
        shield=shield,
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: active)
        )
    )

    result = await ShieldService(
        config=GameConfig(shield_rules=ShieldRules(max_flat_absorption=100))
    ).consume_for_attack(session, user_id=2, incoming_damage=100)

    assert result.blocked_damage == 100
    assert result.remaining_damage == 0
