from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.castle import Castle
from app.models.defense import Defense
from app.models.resource import Resource
from app.models.user import User


class UserRepository:
    async def get_by_telegram_user_id(
        self,
        session: AsyncSession,
        telegram_user_id: int,
        *,
        for_update: bool = False,
    ) -> User | None:
        statement = select(User).where(User.telegram_user_id == telegram_user_id)
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
