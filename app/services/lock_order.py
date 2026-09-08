from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository


async def lock_users_ordered(
    session: AsyncSession,
    users: tuple[User, ...] = (),
    *,
    user_ids: tuple[int, ...] = (),
    repository: UserRepository | None = None,
) -> tuple[User, ...]:
    """Lock User rows in one global order before dependent game entities."""
    user_repository = repository or UserRepository()
    locked: dict[int, User] = {}
    ids = user_ids or tuple(user.id for user in users)
    loader = getattr(user_repository, "get_by_id_for_update", None)
    if loader is None:
        loader = user_repository.get_user_for_update
    for user_id in sorted(set(ids)):
        user = await loader(session, user_id)
        if user is not None:
            locked[user_id] = user
    return tuple(locked[user_id] for user_id in (ids or tuple(user.id for user in users)) if user_id in locked)
