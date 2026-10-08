from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ResourceType
from app.services.shield_service import ShieldDailyLimitReached, ShieldService


@pytest.mark.asyncio
async def test_daily_limit_blocks_third_break_shield_purchase() -> None:
    user = SimpleNamespace(id=4, level=500)
    resources = SimpleNamespace(coin=10000)
    shield = SimpleNamespace(
        id=7,
        name="سپر زنگ تفریح",
        is_active=True,
        unlock_level=1,
        purchase_price=120,
        purchase_resource=ResourceType.COIN,
        duration_minutes=30,
        reduction_percent=0,
        flat_absorption=0,
    )
    records = [user, resources, shield]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda item=item: item)
                for item in records
            ]
            + [SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))]
        ),
        scalar=AsyncMock(return_value=2),
        add=AsyncMock(),
        flush=AsyncMock(),
    )

    with pytest.raises(ShieldDailyLimitReached):
        await ShieldService().buy(session, user.id, shield.id)

    session.scalar.assert_awaited_once()
    query = str(session.scalar.await_args.args[0])
    assert "SHIELD_PURCHASE" in query or "transactions.reason" in query
    session.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_mohammadi_shield_loses_extra_attack_duration() -> None:
    expires = datetime.now(UTC) + timedelta(hours=6)
    active = SimpleNamespace(active_until=expires)
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: active)
        )
    )

    await ShieldService().apply_outgoing_attack_time_penalty(
        session, 4, timedelta(minutes=2)
    )

    assert active.active_until == expires - timedelta(minutes=2)
