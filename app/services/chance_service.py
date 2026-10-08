from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import game_config
from app.models.chance_box import ChanceBox
from app.models.chance_card import ChanceCard
from app.models.user import User
from app.services.reward_service import RewardService, RewardSpec


class ChanceError(RuntimeError):
    pass


class AlreadyClaimed(ChanceError):
    pass


class WrongCaptcha(ChanceError):
    pass


class BoxExpired(ChanceError):
    pass


class CardExpired(ChanceError):
    pass


class ChanceService:
    CARD_VALIDITY = timedelta(hours=1)

    def __init__(self, reward_service: RewardService | None = None) -> None:
        self.reward_service = reward_service or RewardService()

    @staticmethod
    def captcha() -> tuple[str, str]:
        operation = secrets.choice(("+", "−", "×"))
        if operation == "×":
            left, right = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
            result = left * right
        else:
            left, right = secrets.randbelow(19) + 2, secrets.randbelow(19) + 2
            if operation == "−" and left < right:
                left, right = right, left
            result = left + right if operation == "+" else left - right
        return f"{left} {operation} {right} = ؟", str(result)

    @classmethod
    def card_expires_at(cls, card: ChanceCard) -> datetime:
        created_at = card.created_at or datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at + cls.CARD_VALIDITY

    async def create_box(
        self,
        session: AsyncSession,
        group_id: int,
        message_id: int,
        resource: ResourceType,
        amount: int,
        *,
        now: datetime | None = None,
    ) -> ChanceBox:
        if amount < 0:
            raise ValueError("chance box amount cannot be negative")
        now = now or datetime.now(UTC)
        box = ChanceBox(
            group_id=group_id,
            telegram_message_id=message_id,
            resource_type=resource,
            amount=amount,
            expires_at=now
            + timedelta(minutes=game_config.chance_box_rules.expiry_minutes),
        )
        session.add(box)
        await session.flush()
        return box

    async def claim_box(
        self, session: AsyncSession, box_id: int, telegram_user_id: int
    ) -> tuple[ChanceBox, bool]:
        result = await session.execute(
            select(ChanceBox).where(ChanceBox.id == box_id).with_for_update()
        )
        box = result.scalar_one_or_none()
        if box is None or box.claimed_by_user_id is not None:
            raise AlreadyClaimed
        now = datetime.now(UTC)
        expires_at = (
            box.expires_at
            if box.expires_at.tzinfo
            else box.expires_at.replace(tzinfo=UTC)
        )
        if expires_at <= now:
            await session.delete(box)
            await session.flush()
            raise BoxExpired
        result = await session.execute(
            select(User).where(
                User.telegram_user_id == telegram_user_id,
                User.is_active.is_(True),
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ChanceError("user is not registered")
        box.claimed_by_user_id = user.id
        box.claimed_at = datetime.now(UTC)
        await self.reward_service.grant(
            session,
            user_id=user.id,
            spec=RewardSpec(box.resource_type, box.amount),
            source="CHANCE_BOX",
            reference_type="CHANCE_BOX",
            reference_id=box.id,
        )
        await session.flush()
        return box, True

    async def create_card(
        self,
        session: AsyncSession,
        user_id: int,
        resource: ResourceType,
        amount: int,
        answer: str,
    ) -> ChanceCard:
        if amount < 0:
            raise ValueError("chance card amount cannot be negative")
        if not answer.strip():
            raise ValueError("chance card answer cannot be empty")
        card = ChanceCard(
            user_id=user_id,
            resource_type=resource,
            amount=amount,
            captcha_answer=answer,
            captcha_hash=hashlib.sha256(answer.encode()).hexdigest(),
        )
        session.add(card)
        await session.flush()
        return card

    async def claim_card(
        self, session: AsyncSession, card_id: int, user_id: int, answer: str
    ) -> ChanceCard:
        result = await session.execute(
            select(ChanceCard)
            .join(User, User.id == ChanceCard.user_id)
            .where(ChanceCard.id == card_id, ChanceCard.user_id == user_id)
            .where(User.is_active.is_(True))
            .with_for_update()
        )
        card = result.scalar_one_or_none()
        if card is None or card.is_claimed:
            raise AlreadyClaimed
        if self.card_expires_at(card) <= datetime.now(UTC):
            raise CardExpired
        normalized_answer = answer.strip().translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        if not secrets.compare_digest(
            card.captcha_hash,
            hashlib.sha256(normalized_answer.encode()).hexdigest(),
        ):
            # A wrong answer consumes this card without granting its reward.
            card.is_claimed = True
            await session.flush()
            raise WrongCaptcha
        card.is_claimed = True
        card.claimed_at = datetime.now(UTC)
        await self.reward_service.grant(
            session,
            user_id=user_id,
            spec=RewardSpec(card.resource_type, card.amount),
            source="CHANCE_CARD",
            reference_type="CHANCE_CARD",
            reference_id=card.id,
        )
        await session.flush()
        return card
