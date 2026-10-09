from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import game_config
from app.models.chance_box import ChanceBox
from app.models.chance_card import ChanceCard
from app.models.user import User
from app.services.reward_service import RewardService, RewardSpec
from app.services.symbol_captcha import make_symbol_captcha


class ChanceError(RuntimeError):
    pass


class AlreadyClaimed(ChanceError):
    pass


class WrongCaptcha(ChanceError):
    pass


class AlreadyAttempted(ChanceError):
    pass


class BoxExpired(ChanceError):
    pass


class CardExpired(ChanceError):
    pass


def _png_captcha(problem: str) -> bytes:
    """Render a large, evenly centered equation on a clean card."""
    image = Image.new("RGB", (760, 260), "#101d32")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (29, 29, 730, 230), radius=28, fill="#f7f9fc", outline="#d5e0ec", width=3
    )
    font = ImageFont.truetype(
        str(Path(__file__).parent / "assets" / "DejaVuSansMono.ttf"), 82
    )
    bounds = draw.textbbox((0, 0), problem, font=font)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    draw.text(
        ((760 - text_width) / 2 - bounds[0], (260 - text_height) / 2 - bounds[1]),
        problem,
        font=font,
        fill="#172b44",
    )
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


class ChanceService:
    CARD_VALIDITY = timedelta(hours=1)

    def __init__(self, reward_service: RewardService | None = None) -> None:
        self.reward_service = reward_service or RewardService()

    @staticmethod
    def captcha() -> tuple[str, bytes, str]:
        operation = secrets.choice(("+", "−", "×"))
        if operation == "×":
            left, right = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
            result = left * right
        else:
            left, right = secrets.randbelow(19) + 2, secrets.randbelow(19) + 2
            if operation == "−" and left < right:
                left, right = right, left
            result = left + right if operation == "+" else left - right
        problem = f"{left} {operation} {right} = ?"
        return problem, _png_captcha(problem), str(result)

    @staticmethod
    def box_captcha() -> tuple[bytes, str, tuple[str, ...]]:
        return make_symbol_captcha()

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
        captcha_answer: str | None = None,
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
            captcha_answer=captcha_answer,
            expires_at=now
            + timedelta(minutes=game_config.chance_box_rules.expiry_minutes),
        )
        session.add(box)
        await session.flush()
        return box

    async def claim_box(
        self,
        session: AsyncSession,
        box_id: int,
        telegram_user_id: int,
        answer: str | None = None,
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
        if box.captcha_answer is not None:
            from app.models.chance_box_attempt import ChanceBoxAttempt

            if answer is None:
                raise ChanceError("captcha answer is required")
            attempted = await session.scalar(
                select(ChanceBoxAttempt.id).where(
                    ChanceBoxAttempt.box_id == box.id,
                    ChanceBoxAttempt.user_id == user.id,
                )
            )
            if attempted is not None:
                raise AlreadyAttempted
            correct = secrets.compare_digest(box.captcha_answer, answer or "")
            session.add(
                ChanceBoxAttempt(box_id=box.id, user_id=user.id, is_correct=correct)
            )
            await session.flush()
            if not correct:
                raise WrongCaptcha
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
