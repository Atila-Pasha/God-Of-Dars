import asyncio
from uuid import uuid4

from aiogram.types import User as TelegramUser
from sqlalchemy import delete, func, select

from app.db.session import AsyncSessionLocal
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User
from app.services.mine_service import MineService
from app.services.user_service import UserService


async def test_registration_and_first_mine_open_grant_100_each_once():
    telegram_user = TelegramUser(
        id=uuid4().int % 2_000_000_000, first_name="starter", is_bot=False
    )

    async def register():
        async with AsyncSessionLocal() as session:
            user = await UserService().get_or_create_from_telegram(
                session, telegram_user
            )
            await session.commit()
            return user.id

    try:
        ids = await asyncio.gather(*(register() for _ in range(8)))
        assert len(set(ids)) == 1
        assert await register() == ids[0]
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == ids[0])
                )
                == 100
            )
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.user_id == ids[0],
                        Transaction.reason == "STARTER_BONUS",
                    )
                )
                == 1
            )

        async def open_mine():
            async with AsyncSessionLocal() as session:
                await MineService().open(session, ids[0])
                await session.commit()

        await asyncio.gather(*(open_mine() for _ in range(8)))
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == ids[0])
                )
                == 200
            )
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.user_id == ids[0],
                        Transaction.reason == "MINE_ACTIVATION_BONUS",
                        Transaction.amount == 100,
                    )
                )
                == 1
            )
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            uid = await session.scalar(
                select(User.id).where(User.telegram_user_id == telegram_user.id)
            )
            if uid is not None:
                await session.execute(
                    delete(Transaction).where(Transaction.user_id == uid)
                )
                await session.execute(delete(User).where(User.id == uid))
