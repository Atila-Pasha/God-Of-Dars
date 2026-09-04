from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.castle import Castle
from app.models.defense import Defense
from app.models.resource import Resource
from app.models.user import User


class UserRepository:
    async def get_resources_for_update(
        self, session: AsyncSession, user_id: int
    ) -> Resource | None:
        result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self, session: AsyncSession, user_id: int
    ) -> User | None:
        result = await session.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.resources))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_active_by_id(
        self, session: AsyncSession, user_id: int, *, for_update: bool = False
    ) -> User | None:
        statement = (
            select(User)
            .where(User.id == user_id, User.is_active.is_(True))
            .options(selectinload(User.resources))
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_telegram_user_id(
        self,
        session: AsyncSession,
        telegram_user_id: int,
        *,
        for_update: bool = False,
    ) -> User | None:
        statement = (
            select(User)
            .where(User.telegram_user_id == telegram_user_id)
            .options(selectinload(User.resources))
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_by_username(
        self, session: AsyncSession, username: str, *, for_update: bool = False
    ) -> User | None:
        normalized = username.strip().removeprefix("@").casefold()
        statement = (
            select(User)
            .where(User.is_active.is_(True), func.lower(User.username) == normalized)
            .options(selectinload(User.resources))
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        session: AsyncSession,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        # Resource defaults are defined by the model (zero balances). No game
        # balance is invented here.
        user.resources = Resource(coin=0, diamond=0, banana=0)
        # The model requires a castle strength, but the final starting balance
        # is not defined yet. The centralized placeholder is deliberately 0.
        from app.core.game_logic import game_config

        user.castle = Castle(
            strength=game_config.initial_castle_strength,
            defense=Defense(defense_power=game_config.initial_defense_power),
        )
        session.add(user)
        await session.flush()
        return user

    async def update_telegram_profile(
        self,
        session: AsyncSession,
        user: User,
        *,
        username: str | None,
        first_name: str,
        last_name: str | None,
    ) -> User:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        await session.flush()
        return user
