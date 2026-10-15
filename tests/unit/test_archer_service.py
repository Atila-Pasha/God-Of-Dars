from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.archer_service import ArcherError, ArcherService


@pytest.mark.asyncio
async def test_counterfire_uses_one_equipped_arrow_and_caps_damage() -> None:
    service = ArcherService()
    archer = SimpleNamespace(
        level=3,
        archer=SimpleNamespace(name="محسنی", power=8, emoji="123", sticker="sticker"),
    )
    equipped = SimpleNamespace(
        quantity=2,
        is_equipped=True,
        pack=SimpleNamespace(name="افسانه‌ای", power=50),
    )
    reserve = SimpleNamespace(
        quantity=5,
        is_equipped=False,
        pack=SimpleNamespace(name="ساده", power=2),
    )
    service.owned = AsyncMock(return_value=[archer])
    service.ammunition = AsyncMock(return_value=[equipped, reserve])

    hit = await service.fire(
        object(), 1, teacher_hp=80, teacher_max_hp=80, shot_index=0
    )

    assert hit is not None
    assert hit.damage == 24  # Maximum 30% of the teacher's maximum HP.
    assert hit.name == "محسنی"
    assert equipped.quantity == 1
    assert reserve.quantity == 5


@pytest.mark.asyncio
async def test_counterfire_stops_when_equipped_pack_is_empty() -> None:
    service = ArcherService()
    service.owned = AsyncMock(
        return_value=[SimpleNamespace(level=1, archer=SimpleNamespace(power=4))]
    )
    service.ammunition = AsyncMock(
        return_value=[SimpleNamespace(quantity=5, is_equipped=False)]
    )

    assert await service.fire(object(), 1, 80, 80, 0) is None


@pytest.mark.asyncio
async def test_second_archer_requires_selling_the_first() -> None:
    service = ArcherService()
    service._buyer = AsyncMock(return_value=(SimpleNamespace(level=5), object()))
    service.owned = AsyncMock(return_value=[object()])
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(is_active=True, unlock_level=1)),
        scalar=AsyncMock(return_value=None),
    )

    with pytest.raises(ArcherError, match="بفروشید"):
        await service.buy_archer(session, 1, 2)
