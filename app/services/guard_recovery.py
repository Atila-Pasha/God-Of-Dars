"""Shared five-hour recovery for the two castle guards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.archer import UserArcher
    from app.models.knight import UserKnight

GUARD_RECOVERY_TIME = timedelta(hours=5)


def restore_if_ready(
    guard: UserArcher | UserKnight, maximum_hp: int, *, now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    if guard.recovery_until is not None and guard.recovery_until <= now:
        guard.current_hp = maximum_hp
        guard.recovery_until = None
    return guard.recovery_until is None and guard.current_hp > 0


def take_damage(
    guard: UserArcher | UserKnight, damage: int, *, now: datetime | None = None
) -> bool:
    """Return true only when this hit starts a new recovery period."""
    guard.current_hp = max(0, guard.current_hp - max(0, damage))
    if guard.current_hp != 0 or guard.recovery_until is not None:
        return False
    guard.recovery_until = (now or datetime.now(UTC)) + GUARD_RECOVERY_TIME
    return True
