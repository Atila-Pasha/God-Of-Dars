from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group


class GroupRepository:
    async def get_by_telegram_chat_id(
        self, session: AsyncSession, telegram_chat_id: int
    ) -> Group | None:
        result = await session.execute(
            select(Group).where(Group.telegram_chat_id == telegram_chat_id)
        )
        return result.scalar_one_or_none()

    async def register_chat(
        self,
        session: AsyncSession,
        *,
        telegram_chat_id: int,
        title: str,
        username: str | None,
    ) -> Group:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            statement = postgres_insert(Group).values(
                telegram_chat_id=telegram_chat_id,
                title=title,
                username=username,
                is_active=True,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[Group.telegram_chat_id],
                set_={
                    "title": statement.excluded.title,
                    "username": statement.excluded.username,
                    "is_active": True,
                },
            )
            await session.execute(statement)
            group = await self.get_by_telegram_chat_id(session, telegram_chat_id)
            if group is None:
                raise RuntimeError("Group registration did not return a group")
            return group

        group = await self.get_by_telegram_chat_id(session, telegram_chat_id)
        if group is None:
            group = Group(
                telegram_chat_id=telegram_chat_id,
                title=title,
                username=username,
                is_active=True,
            )
            session.add(group)
        else:
            group.title = title
            group.username = username
            group.is_active = True
        await session.flush()
        return group
