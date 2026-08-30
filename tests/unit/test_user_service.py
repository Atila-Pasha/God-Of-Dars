from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.resource import Resource
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.user_service import UserInitializationError, UserService


def telegram_user(**overrides: object) -> TelegramUser:
    values = {
        "id": 42,
        "is_bot": False,
        "first_name": "Ali",
        "last_name": "Pasha",
        "username": "ali",
    }
    values.update(overrides)
    return TelegramUser(**values)


@pytest.mark.asyncio
async def test_new_user_is_created_once() -> None:
    repository = AsyncMock()
    repository.get_by_telegram_user_id.return_value = None
    created_user = User(
        telegram_user_id=42,
        first_name="Ali",
        last_name="Pasha",
        username="ali",
    )
    repository.create.return_value = created_user
    session = AsyncMock()

    result = await UserService(repository).get_or_create_from_telegram(
        session, telegram_user()
    )

    assert result is created_user
    repository.create.assert_awaited_once_with(
        session,
        telegram_user_id=42,
        username="ali",
        first_name="Ali",
        last_name="Pasha",
    )


@pytest.mark.asyncio
async def test_existing_user_profile_is_updated_without_duplicate() -> None:
    repository = AsyncMock()
    existing_user = User(
        telegram_user_id=42,
        first_name="Old",
        last_name=None,
        username=None,
    )
    repository.get_by_telegram_user_id.return_value = existing_user
    session = AsyncMock()

    result = await UserService(repository).get_or_create_from_telegram(
        session, telegram_user()
    )

    assert result is existing_user
    repository.create.assert_not_awaited()
    repository.update_telegram_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_failure_is_safe() -> None:
    repository = AsyncMock()
    repository.get_by_telegram_user_id.side_effect = SQLAlchemyError("secret")
    session = AsyncMock()

    with pytest.raises(UserInitializationError):
        await UserService(repository).get_or_create_from_telegram(
            session, telegram_user()
        )

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_creation_race_reuses_existing_user() -> None:
    repository = AsyncMock()
    existing_user = User(
        telegram_user_id=42,
        first_name="Ali",
        last_name="Pasha",
        username="ali",
    )
    repository.get_by_telegram_user_id.side_effect = [None, existing_user]
    repository.create.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    session = AsyncMock()

    result = await UserService(repository).get_or_create_from_telegram(
        session, telegram_user()
    )

    assert result is existing_user
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_repository_initializes_only_model_default_resources() -> None:
    session = MagicMock()
    session.flush = AsyncMock()

    user = await UserRepository().create(
        session,
        telegram_user_id=42,
        username="ali",
        first_name="Ali",
        last_name="Pasha",
    )

    assert isinstance(user.resources, Resource)
    assert user.resources.coin == 0
    assert user.resources.diamond == 0
    assert user.resources.banana == 0
