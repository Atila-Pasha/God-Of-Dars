from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.core.game_logic import game_config
from app.repositories.user import UserRepository
from app.services.admin_service import AdminService


async def test_delete_teacher_removes_all_user_ownership_before_catalog_row() -> None:
    first_ownership = SimpleNamespace(id=11)
    second_ownership = SimpleNamespace(id=12)
    teacher = SimpleNamespace(
        id=7,
        is_active=True,
        owned_by_users=[first_ownership, second_ownership],
    )
    scalars = SimpleNamespace(
        unique=lambda: SimpleNamespace(one_or_none=lambda: teacher)
    )
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: scalars)

    deleted, returned_teacher = await AdminService().delete_teacher(session, 7)

    assert deleted is True
    assert returned_teacher is teacher
    assert teacher.is_active is False
    assert session.delete.await_args_list == [
        call(first_ownership),
        call(second_ownership),
        call(teacher),
    ]
    assert session.flush.await_count == 2


async def test_delete_teacher_returns_not_found_without_deleting() -> None:
    scalars = SimpleNamespace(unique=lambda: SimpleNamespace(one_or_none=lambda: None))
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: scalars)

    deleted, teacher = await AdminService().delete_teacher(session, 404)

    assert deleted is False
    assert teacher is None
    session.delete.assert_not_awaited()
    session.flush.assert_not_awaited()


async def test_admin_increases_level_without_spending_xp(monkeypatch) -> None:
    user = SimpleNamespace(level=10, resources=SimpleNamespace(banana=123))
    locked_lookup = AsyncMock(return_value=user)
    monkeypatch.setattr(UserRepository, "get_by_id_for_update", locked_lookup)
    session = AsyncMock()

    result = await AdminService().increase_user_level(session, 42, 3)

    assert result == (user, 10)
    assert user.level == 13
    assert user.resources.banana == 123
    locked_lookup.assert_awaited_once_with(session, 42)
    session.flush.assert_awaited_once()


async def test_admin_level_increase_rejects_exceeding_game_cap(monkeypatch) -> None:
    max_level = game_config.level_progression.max_level
    user = SimpleNamespace(level=max_level - 1)
    monkeypatch.setattr(
        UserRepository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    session = AsyncMock()

    with pytest.raises(ValueError, match="حداکثر لول"):
        await AdminService().increase_user_level(session, 42, 2)

    assert user.level == max_level - 1
    session.flush.assert_not_awaited()
