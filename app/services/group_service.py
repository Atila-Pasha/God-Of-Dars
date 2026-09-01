from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group
from app.repositories.group import GroupRepository


class GroupService:
    def __init__(self, repository: GroupRepository | None = None) -> None:
        self.repository = repository or GroupRepository()

    async def register_chat(
        self,
        session: AsyncSession,
        *,
        telegram_chat_id: int,
        title: str,
        username: str | None,
    ) -> Group:
        return await self.repository.register_chat(
            session,
            telegram_chat_id=telegram_chat_id,
            title=title,
            username=username,
        )
