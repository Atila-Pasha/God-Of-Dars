from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ResourceType
from app.services.teacher_service import TeacherCapacity, TeacherService


@pytest.mark.asyncio
async def test_buyable_catalog_respects_level_capacity_balance_and_ownership() -> None:
    def teacher(
        id_: int,
        *,
        level: int = 1,
        price: int = 10,
        resource: ResourceType = ResourceType.COIN,
        damage: int = 10,
    ):
        return SimpleNamespace(
            id=id_,
            unlock_level=level,
            purchase_price=price,
            purchase_resource=resource,
            damage=damage,
            is_active=True,
        )

    available = teacher(1)
    catalog = [
        available,
        teacher(2, level=4),
        teacher(3, price=101),
        teacher(4, resource=ResourceType.DIAMOND, price=11),
        teacher(5, damage=1000),
    ]
    repository = SimpleNamespace(
        get_user=AsyncMock(return_value=SimpleNamespace(level=3)),
        get_resources=AsyncMock(return_value=SimpleNamespace(coin=100, diamond=10)),
        list_catalog=AsyncMock(return_value=catalog),
    )
    service = TeacherService(repository=repository)
    service.capacity = AsyncMock(
        return_value=TeacherCapacity(
            owned=0, available=10, maximum=100, percent_based=True
        )
    )

    result = await service.buyable_catalog(AsyncMock(), 7)

    assert result == [available]
    repository.list_catalog.assert_awaited_once()
