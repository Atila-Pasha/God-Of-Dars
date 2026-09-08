from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.castle import Castle
from app.models.resource import Resource
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


async def lock_attack_dependencies(
    session: AsyncSession,
    users: tuple[User, ...],
) -> tuple[dict[int, Resource], dict[int, Castle]]:
    """Lock attack resources, then castles, in ascending user-id order."""
    user_ids = sorted({user.id for user in users})
    resources = {
        row.user_id: row
        for row in (
            await session.scalars(
                select(Resource)
                .where(Resource.user_id.in_(user_ids))
                .order_by(Resource.user_id)
                .with_for_update()
            )
        )
    }
    castles = {
        row.user_id: row
        for row in (
            await session.scalars(
                select(Castle)
                .where(Castle.user_id.in_(user_ids))
                .options(selectinload(Castle.defense))
                .order_by(Castle.user_id)
                .with_for_update()
            )
        )
    }
    for user in users:
        if user.id in resources:
            set_committed_value(user, "resources", resources[user.id])
    return resources, castles
