from uuid import uuid4

import pytest

from app.core.enums import ResourceType
from app.db.session import AsyncSessionLocal
from app.models.archer import Archer, ArrowPack
from app.models.resource import Resource
from app.models.user import User
from app.services.archer_service import ArcherError, ArcherService


@pytest.mark.asyncio
async def test_buy_fire_sell_and_replace_archer() -> None:
    async with AsyncSessionLocal() as session:
        await session.begin()
        try:
            user = User(
                telegram_user_id=int(uuid4().int % 2_000_000_000),
                first_name="archer-test",
                level=3,
            )
            resources = Resource(user=user, coin=1000, diamond=100)
            first = Archer(
                name=f"first-{uuid4().hex[:8]}",
                power=4,
                purchase_price=250,
                purchase_resource=ResourceType.COIN,
                upgrade_price=25,
                unlock_level=2,
            )
            second = Archer(
                name=f"second-{uuid4().hex[:8]}",
                power=7,
                purchase_price=400,
                purchase_resource=ResourceType.COIN,
                upgrade_price=50,
                unlock_level=3,
            )
            pack = ArrowPack(
                name=f"pack-{uuid4().hex[:8]}",
                power=2,
                quantity=2,
                purchase_price=30,
                purchase_resource=ResourceType.COIN,
                unlock_level=2,
            )
            session.add_all((user, resources, first, second, pack))
            await session.flush()
            service = ArcherService()

            owned = await service.buy_archer(session, user.id, first.id)
            with pytest.raises(ArcherError, match="بفروشید"):
                await service.buy_archer(session, user.id, second.id)
            ammunition = await service.buy_pack(session, user.id, pack.id)
            assert ammunition.is_equipped and ammunition.quantity == 2
            hit = await service.fire(session, user.id, 80, 80, 0)
            assert hit is not None and hit.damage == 6
            assert ammunition.quantity == 1

            upgraded = await service.upgrade(session, user.id, owned.id)
            assert upgraded.level == 2 and service.power(upgraded) == 5
            name, refund, currency = await service.sell(session, user.id, owned.id)
            assert (
                name == first.name and refund == 125 and currency is ResourceType.COIN
            )
            replacement = await service.buy_archer(session, user.id, second.id)
            assert replacement.archer_id == second.id
            assert len(await service.owned(session, user.id)) == 1
        finally:
            await session.rollback()
