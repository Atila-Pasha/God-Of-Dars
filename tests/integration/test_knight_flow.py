from uuid import uuid4

import pytest

from app.core.enums import ResourceType
from app.db.session import AsyncSessionLocal
from app.models.archer import Archer, ArrowPack
from app.models.knight import Knight
from app.models.resource import Resource
from app.models.user import User
from app.services.archer_service import ArcherService
from app.services.knight_service import KnightService


@pytest.mark.asyncio
async def test_knight_and_archer_selection_and_persistent_health() -> None:
    async with AsyncSessionLocal() as session:
        await session.begin()
        try:
            user = User(
                telegram_user_id=int(uuid4().int % 2_000_000_000),
                first_name="knight-test",
                level=5,
            )
            resources = Resource(user=user, coin=2000, diamond=100)
            archer = Archer(
                name=f"archer-{uuid4().hex[:8]}",
                power=4,
                purchase_price=100,
                purchase_resource=ResourceType.COIN,
                upgrade_price=10,
                unlock_level=1,
            )
            knight = Knight(
                name=f"knight-{uuid4().hex[:8]}",
                power=8,
                max_hp=20,
                purchase_price=150,
                purchase_resource=ResourceType.COIN,
                upgrade_price=10,
                unlock_level=1,
            )
            arrows = ArrowPack(
                name=f"arrows-{uuid4().hex[:8]}",
                power=2,
                quantity=3,
                purchase_price=20,
                purchase_resource=ResourceType.COIN,
                unlock_level=1,
            )
            session.add_all((user, resources, archer, knight, arrows))
            await session.flush()

            archers = ArcherService()
            knights = KnightService()
            owned_archer = await archers.buy_archer(session, user.id, archer.id)
            stock = await archers.buy_pack(session, user.id, arrows.id)
            owned_knight = await knights.buy(session, user.id, knight.id)
            assert owned_archer.is_equipped and not owned_knight.is_equipped
            assert await knights.reduction(session, user.id) == 0

            await knights.equip(session, user.id, "knight")
            assert owned_knight.is_equipped and not owned_archer.is_equipped
            assert await knights.reduction(session, user.id) == 16
            for _ in range(2):
                hit = await archers.fire(session, user.id, 80, 80, 0, 20)
                assert hit is not None and hit.arrow_name == "شمشیر"
                assert hit.damage == 8
                assert hit.reduction == 16
            assert owned_knight.current_hp == 10
            assert stock.quantity == 3
            upgraded = await knights.upgrade(session, user.id, owned_knight.id)
            assert upgraded.current_hp == 10
            assert knights.max_hp(upgraded) == 22

            await knights.equip(session, user.id, "archer")
            assert owned_archer.is_equipped and not owned_knight.is_equipped
            hit = await archers.fire(session, user.id, 80, 80, 0)
            assert hit is not None and hit.arrow_name == arrows.name
            assert stock.quantity == 2
            assert owned_knight.current_hp == 10

            await knights.equip(session, user.id, "knight")
            final_hit = None
            for _ in range(2):
                final_hit = await archers.fire(session, user.id, 80, 80, 0, 20)
                assert final_hit is not None
            assert final_hit.died
            assert owned_knight.current_hp == 0
            assert await knights.owned(session, user.id) is None
            assert await archers.fire(session, user.id, 80, 80, 0, 20) is None
            assert await knights.reduction(session, user.id) == 0
            assert stock.quantity == 2

            await knights.equip(session, user.id, "archer")
            assert owned_archer.is_equipped
            replacement = await knights.buy(session, user.id, knight.id)
            assert replacement.current_hp == 20 and not replacement.is_equipped
        finally:
            await session.rollback()
