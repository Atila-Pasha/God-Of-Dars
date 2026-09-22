from datetime import UTC, datetime
from secrets import randbelow

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.castle import Castle
from app.models.defense import Defense
from app.models.resource import Resource
from app.models.user import User
from app.models.user_shield import UserShield


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
            .execution_options(populate_existing=True)
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

    async def list_active_levels_by_proximity(
        self, session: AsyncSession, *, level: int, exclude_user_id: int
    ) -> list[int]:
        """Return populated levels nearest to a player without scanning users."""
        now = datetime.now(UTC)
        active_shield = (
            select(UserShield.id)
            .where(
                UserShield.user_id == User.id,
                UserShield.active_until.is_not(None),
                UserShield.active_until > now,
            )
            .exists()
        )
        result = await session.scalars(
            select(User.level)
            .where(
                User.is_active.is_(True),
                User.id != exclude_user_id,
                ~active_shield,
            )
            .group_by(User.level)
            .order_by(func.abs(User.level - level), User.level)
        )
        return list(result)

    async def pick_random_active_at_level(
        self,
        session: AsyncSession,
        *,
        level: int,
        exclude_user_id: int,
        exclude_target_id: int | None = None,
    ) -> User | None:
        """Pick an indexed, approximately uniform random user at one level.

        ``ORDER BY random()`` becomes increasingly expensive as the user table
        grows. Picking an id pivot keeps the query index-friendly; a possible
        id gap only causes a harmless small distribution bias.
        """
        conditions = [
            User.is_active.is_(True),
            User.level == level,
            User.id != exclude_user_id,
            ~select(UserShield.id)
            .where(
                UserShield.user_id == User.id,
                UserShield.active_until.is_not(None),
                UserShield.active_until > datetime.now(UTC),
            )
            .exists(),
        ]
        if exclude_target_id is not None:
            conditions.append(User.id != exclude_target_id)
        lower_id, upper_id = (
            await session.execute(
                select(func.min(User.id), func.max(User.id)).where(*conditions)
            )
        ).one()
        if lower_id is None or upper_id is None:
            return None
        pivot = lower_id + randbelow(upper_id - lower_id + 1)
        statement = (
            select(User)
            .where(*conditions, User.id >= pivot)
            .options(selectinload(User.resources))
            .order_by(User.id)
            .limit(1)
        )
        target = await session.scalar(statement)
        if target is not None:
            return target
        return await session.scalar(
            select(User)
            .where(*conditions, User.id < pivot)
            .options(selectinload(User.resources))
            .order_by(User.id.desc())
            .limit(1)
        )

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
