from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import (
    BuffetConversion,
    GameConfig,
    GameConfigurationError,
    game_config,
)
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User


class BuffetError(RuntimeError):
    pass


class BuffetUserNotFound(BuffetError):
    pass


class InvalidBuffetConversion(BuffetError):
    pass


class InsufficientResource(BuffetError):
    pass


class ConversionAmountError(BuffetError):
    pass


@dataclass(frozen=True)
class ExchangeResult:
    conversion: BuffetConversion
    packages: int
    source_balance: int
    target_balance: int


class BuffetService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config

    def options(self) -> tuple[BuffetConversion, ...]:
        return self.config.buffet_options()

    async def resources(self, session: AsyncSession, user_id: int) -> Resource | None:
        result = await session.execute(
            select(Resource).where(Resource.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def exchange(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        source: ResourceType,
        target: ResourceType,
        source_amount: int,
    ) -> ExchangeResult:
        if source_amount <= 0:
            raise ConversionAmountError("مقدار تبدیل باید بیشتر از صفر باشد.")
        try:
            conversion = self.config.buffet_conversion(source, target)
        except GameConfigurationError as exc:
            raise InvalidBuffetConversion("این تبدیل در بوفه فعال نیست.") from exc
        if source_amount % conversion.source_amount:
            raise ConversionAmountError(
                f"مقدار باید مضربی از {conversion.source_amount} باشد."
            )

        user_result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user_result.scalar_one_or_none() is None:
            raise BuffetUserNotFound
        resource_result = await session.execute(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        resources = resource_result.scalar_one_or_none()
        if resources is None:
            raise BuffetUserNotFound

        source_field = source.value.lower()
        target_field = target.value.lower()
        source_balance = getattr(resources, source_field)
        if source_balance < source_amount:
            raise InsufficientResource(
                f"موجودی {source.value} برای این تبدیل کافی نیست."
            )
        old_target_balance = getattr(resources, target_field)
        target_balance = (
            old_target_balance
            + (source_amount // conversion.source_amount) * conversion.target_amount
        )
        new_source_balance = source_balance - source_amount
        setattr(resources, source_field, new_source_balance)
        setattr(resources, target_field, target_balance)
        session.add_all(
            [
                Transaction(
                    user_id=user_id,
                    resource_type=source,
                    amount=-source_amount,
                    balance_before=source_balance,
                    balance_after=new_source_balance,
                    reason="BUFFET_EXCHANGE",
                ),
                Transaction(
                    user_id=user_id,
                    resource_type=target,
                    amount=target_balance - old_target_balance,
                    balance_before=old_target_balance,
                    balance_after=target_balance,
                    reason="BUFFET_EXCHANGE",
                ),
            ]
        )
        await session.flush()
        return ExchangeResult(
            conversion=conversion,
            packages=source_amount // conversion.source_amount,
            source_balance=new_source_balance,
            target_balance=target_balance,
        )
