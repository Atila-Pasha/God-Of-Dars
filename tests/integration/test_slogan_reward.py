"""The 30-minute slogan cannot be claimed twice, even from parallel updates."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User
from app.services.slogan_service import SloganService

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"), reason="requires PostgreSQL"
)


@pytest.mark.asyncio
async def test_slogan_reward_is_atomic_and_persists_across_sessions() -> None:
    await engine.dispose()
    telegram_id = int(uuid4().int % 2_000_000_000)
    async with AsyncSessionLocal() as session, session.begin():
        user = User(telegram_user_id=telegram_id, first_name="slogan-test")
        user.resources = Resource(coin=0, diamond=0, banana=0)
        session.add(user)
        await session.flush()
        user_id = user.id

    service = SloganService()
    now = datetime.now(UTC)

    async def claim(at: datetime):
        async with AsyncSessionLocal() as session, session.begin():
            return await service.claim(session, telegram_id, now=at)

    first, second = await asyncio.gather(claim(now), claim(now))
    assert sum(result.awarded for result in (first, second)) == 1
    assert (
        next(result for result in (first, second) if result.awarded).current_banana == 3
    )
    assert sorted(result.retry_after_seconds for result in (first, second)) == [0, 1800]

    before_reset = await claim(now + timedelta(seconds=1799))
    at_reset = await claim(now + timedelta(seconds=1800))
    assert before_reset.retry_after_seconds == 1
    assert at_reset.awarded
    assert at_reset.current_banana == 6

    async with AsyncSessionLocal() as session:
        balance = await session.scalar(
            select(Resource.banana).where(Resource.user_id == user_id)
        )
        ledger_count = await session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user_id,
                Transaction.reason == "SLOGAN_REWARD",
            )
        )
        timestamp = await session.scalar(
            select(User.last_slogan_at).where(User.id == user_id)
        )
    assert balance == 6
    assert ledger_count == 2
    assert timestamp == now + timedelta(minutes=30)
    await engine.dispose()
