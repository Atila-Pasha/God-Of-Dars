from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.profile import ProfileRepository, ProfileSnapshot


class ProfileNotFound(RuntimeError):
    pass


class ProfileService:
    def __init__(self, repository: ProfileRepository | None = None) -> None:
        self.repository = repository or ProfileRepository()

    async def snapshot(
        self, session: AsyncSession, user_id: int
    ) -> ProfileSnapshot:
        snapshot = await self.repository.get_snapshot(session, user_id)
        if snapshot is None:
            raise ProfileNotFound
        return snapshot
