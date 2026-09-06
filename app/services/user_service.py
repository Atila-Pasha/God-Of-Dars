from aiogram.types import User as TelegramUser
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.school_errors import SchoolUserNotFound


class UserInitializationError(RuntimeError):
    pass


class UserInactiveError(RuntimeError):
    pass


class UserService:
    def __init__(self, repository: UserRepository | None = None) -> None:
        self.repository = repository or UserRepository()

    async def get_or_create_from_telegram(
        self, session: AsyncSession, telegram_user: TelegramUser
    ) -> User:
        try:
            user = await self.repository.get_by_telegram_user_id(
                session, telegram_user.id
            )
            if user is not None:
                user.__dict__["_was_created"] = False
                if self._profile_changed(user, telegram_user):
                    await self.repository.update_telegram_profile(
                        session,
                        user,
                        username=telegram_user.username,
                        first_name=telegram_user.first_name,
                        last_name=telegram_user.last_name,
                    )
                if user.is_active is False:
                    raise UserInactiveError
                return user

            try:
                user = await self.repository.create(
                    session,
                    telegram_user_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name,
                )
            except IntegrityError:
                await session.rollback()
                user = await self.repository.get_by_telegram_user_id(
                    session, telegram_user.id
                )
                if user is None:
                    raise UserInitializationError from None
                if self._profile_changed(user, telegram_user):
                    await self.repository.update_telegram_profile(
                        session,
                        user,
                        username=telegram_user.username,
                        first_name=telegram_user.first_name,
                        last_name=telegram_user.last_name,
                    )
                if user.is_active is False:
                    raise UserInactiveError from None
                user.__dict__["_was_created"] = False
                return user

            if user.is_active is False:
                raise UserInactiveError
            user.__dict__["_was_created"] = True
            return user
        except UserInactiveError:
            raise
        except UserInitializationError:
            raise
        except SQLAlchemyError as exc:
            await session.rollback()
            raise UserInitializationError from exc

    async def get_active_by_telegram_user_id(
        self, session: AsyncSession, telegram_user_id: int
    ) -> User:
        try:
            user = await self.repository.get_by_telegram_user_id(
                session, telegram_user_id
            )
        except SQLAlchemyError as exc:
            raise UserInitializationError from exc
        if user is None:
            raise SchoolUserNotFound
        if user.is_active is False:
            raise UserInactiveError
        return user

    @staticmethod
    def _profile_changed(user: User, telegram_user: TelegramUser) -> bool:
        return (
            user.username != telegram_user.username
            or user.first_name != telegram_user.first_name
            or user.last_name != telegram_user.last_name
        )
