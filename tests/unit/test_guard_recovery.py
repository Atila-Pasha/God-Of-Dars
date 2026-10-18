from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.archer_service import ArcherService
from app.services.guard_recovery import restore_if_ready, take_damage


def test_guard_returns_with_full_health_exactly_five_hours_after_falling() -> None:
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    guard = SimpleNamespace(current_hp=10, recovery_until=None)

    assert take_damage(guard, 10, now=now)
    assert guard.current_hp == 0
    assert guard.recovery_until == now + timedelta(hours=5)
    assert not restore_if_ready(
        guard, 100, now=now + timedelta(hours=5) - timedelta(seconds=1)
    )
    assert guard.current_hp == 0
    assert restore_if_ready(guard, 100, now=now + timedelta(hours=5))
    assert guard.current_hp == 100
    assert guard.recovery_until is None


@pytest.mark.asyncio
async def test_archer_loses_health_even_when_out_of_arrows() -> None:
    service = ArcherService()
    archer = SimpleNamespace(
        current_hp=100,
        recovery_until=None,
        is_equipped=True,
    )
    service.owned = AsyncMock(return_value=[archer])
    service.ammunition = AsyncMock(return_value=[])

    hit = await service.fire(object(), 1, 50, 50, 0, incoming_power=400)

    assert hit is None
    assert archer.current_hp == 0
    assert archer.recovery_until is not None
