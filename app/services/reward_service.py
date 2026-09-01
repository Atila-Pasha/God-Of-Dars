from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.resource import Resource
from app.models.reward import Reward
from app.models.transaction import Transaction
from app.repositories.reward import RewardRepository
from app.services.library_errors import RewardNotConfigured
from app.services.resource_service import ResourceService


@dataclass(frozen=True)
class RewardSpec:
    """A reward policy supplied by game design/configuration.

    Library does not provide a default amount.  ``None`` policy means that no
    reward is granted until the game config defines one.
    """

    resource_type: ResourceType
    amount: int

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("reward amount must be non-negative")


@dataclass(frozen=True)
class RewardResult:
    reward: Reward
    created: bool


class RewardService:
    """Persist an idempotent reward and its resource transaction atomically."""

    def __init__(self, repository: RewardRepository | None = None) -> None:
        self.repository = repository or RewardRepository()

    async def grant(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        spec: RewardSpec | None,
        source: str,
        reference_type: str,
        reference_id: int,
    ) -> RewardResult | None:
        if spec is None:
            return None

        existing = await self.repository.get_by_reference(
            session,
            user_id=user_id,
            source=source,
            reference_type=reference_type,
            reference_id=reference_id,
            resource_type=spec.resource_type,
            for_update=True,
        )
        if existing is not None:
            return RewardResult(reward=existing, created=False)

        resources = await self._resources_for_update(session, user_id)
        if resources is None:
            raise RewardNotConfigured

        field = spec.resource_type.value.lower()
        before = getattr(resources, field)
        after = before + spec.amount
        if spec.resource_type is ResourceType.COIN:
            ResourceService.credit_coin(
                session,
                resources,
                user_id=user_id,
                amount=spec.amount,
                reason=source,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        else:
            setattr(resources, field, after)
            session.add(
                Transaction(
                    user_id=user_id,
                    resource_type=spec.resource_type,
                    amount=spec.amount,
                    balance_before=before,
                    balance_after=after,
                    reason=source,
                    reference_type=reference_type,
                    reference_id=reference_id,
                )
            )

        reward = Reward(
            user_id=user_id,
            source=source,
            resource_type=spec.resource_type,
            amount=spec.amount,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        session.add(reward)
        await session.flush()
        return RewardResult(reward=reward, created=True)

    @staticmethod
    async def _resources_for_update(
        session: AsyncSession, user_id: int
    ) -> Resource | None:
        result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()
