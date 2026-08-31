from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.castle import Castle
from app.models.defense import Defense
from app.models.resource import Resource
from app.models.user import User


class CastleRepository:
    async def get_user_for_update(
        self, session: AsyncSession, user_id: int
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_resources_for_update(
        self, session: AsyncSession, user_id: int
    ) -> Resource | None:
        result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self, session: AsyncSession, user_id: int, *, for_update: bool = False
    ) -> Castle | None:
        statement = (
            select(Castle)
            .where(Castle.user_id == user_id)
            .options(selectinload(Castle.defense))
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.unique().scalar_one_or_none()

    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        strength: int,
        defense_power: int,
    ) -> Castle:
        castle = Castle(
            user_id=user_id,
            strength=strength,
            defense=Defense(defense_power=defense_power),
        )
        session.add(castle)
        await session.flush()
        return castle
