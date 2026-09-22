from types import SimpleNamespace
from unittest.mock import AsyncMock, call

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
