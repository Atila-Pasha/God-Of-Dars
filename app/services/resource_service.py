from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.services.school_errors import InsufficientCoins, ResourceNotFound


class ResourceService:
    @staticmethod
    def debit_coin(
        session: AsyncSession,
        resources: Resource | None,
        *,
        user_id: int,
        amount: int,
        reason: str,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> None:
        if resources is None:
            raise ResourceNotFound
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if resources.coin < amount:
            raise InsufficientCoins

        before = resources.coin
        resources.coin -= amount
        session.add(
            Transaction(
                user_id=user_id,
                resource_type=ResourceType.COIN,
                amount=-amount,
                balance_before=before,
                balance_after=resources.coin,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        )

    @staticmethod
    def credit_coin(
        session: AsyncSession,
        resources: Resource | None,
        *,
        user_id: int,
        amount: int,
        reason: str,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> None:
        if resources is None:
            raise ResourceNotFound
        if amount < 0:
            raise ValueError("amount must be non-negative")

        before = resources.coin
        resources.coin += amount
        session.add(
            Transaction(
                user_id=user_id,
                resource_type=ResourceType.COIN,
                amount=amount,
                balance_before=before,
                balance_after=resources.coin,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        )
