"""Car-game identity checks and exactly-once wallet settlement."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.car_game import CarGame
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User
from app.services.car_game_service import (
    CarGameError,
    act,
    create_game,
    now,
    settle_due_game,
)


@pytest.mark.asyncio
async def test_car_crash_credits_wallet_once_and_rejects_other_widget() -> None:
    async with AsyncSessionLocal() as session:
        user = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="car game test",
            resources=Resource(coin=100, diamond=0),
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(session, user_id)
            game.message_id = 99
            game_id = game.id
            await session.commit()
            with pytest.raises(CarGameError):
                await act(session, game_id, user_id + 1, 99, "start")
            with pytest.raises(CarGameError):
                await act(session, game_id, user_id, 100, "start")
            game, _ = await act(session, game_id, user_id, 99, "start")
            assert game.status == "active"
            game, _ = await act(session, game_id, user_id, 99, "lane0")
            assert game.lane == 0
            with pytest.raises(CarGameError):
                await act(session, game_id, user_id, 99, "lane2")
            await session.commit()
        async with AsyncSessionLocal() as session:
            game = await session.get(CarGame, game_id)
            game.seed = 1
            game.lane = 1
            game.tick = 4  # Seed 1 puts an obstacle in lane 1 on this tick.
            game.coin = 2
            game.diamond = 1
            game.started_at = now() - timedelta(seconds=10)
            game.next_tick_at = now() - timedelta(seconds=1)
            await session.commit()

        async def collide() -> bool:
            async with AsyncSessionLocal() as session:
                game, crashed = await act(session, game_id, user_id, 99, "sync")
                await session.commit()
                assert game.status == "crashed"
                return crashed

        assert (await asyncio.gather(collide(), collide())).count(True) == 1
        async with AsyncSessionLocal() as session:
            assert await settle_due_game(session, game_id) is None
            balance = await session.scalar(
                select(Resource).where(Resource.user_id == user_id)
            )
            assert (balance.coin, balance.diamond) == (102, 1)
            entries = (
                await session.scalars(
                    select(Transaction).where(
                        Transaction.user_id == user_id,
                        Transaction.reference_type == "car_game",
                        Transaction.reference_id == game_id,
                    )
                )
            ).all()
            assert sorted(entry.amount for entry in entries) == [1, 2]
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Transaction).where(Transaction.user_id == user_id)
            )
            await session.execute(delete(CarGame).where(CarGame.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
