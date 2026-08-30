from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource import Resource
from app.models.user import User


class UserRepository:
    async def get_by_telegram_user_id(
        self, session: AsyncSession, telegram_user_id: int
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
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
