from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import GameConfig, GameConfigurationError, game_config
from app.repositories.user import UserRepository
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    OperationNotConfigured,
    ResourceNotFound,
    SchoolUserNotFound,
)


class LevelService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config
        self.repository = UserRepository()

    def upgrade_cost(self, level: int) -> int:
        try:
            return self.config.level_progression.upgrade_cost(level)
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc

    async def upgrade(self, session: AsyncSession, user_id: int):
        user = await self.repository.get_by_id_for_update(session, user_id)
        if user is None:
            raise SchoolUserNotFound
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        cost = self.upgrade_cost(user.level)
        ResourceService.debit(
            session, resources, user_id=user.id, resource_type=ResourceType.DIAMOND,
            amount=cost, reason="LEVEL_UPGRADE", reference_type="USER", reference_id=user.id,
        )
        user.level += 1
        await session.flush()
        return user
