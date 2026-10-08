from __future__ import annotations

import hashlib
import secrets
import struct
import zlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import game_config
from app.models.chance_box import ChanceBox
from app.models.chance_card import ChanceCard
from app.models.user import User
from app.services.letter_captcha import make_letter_captcha
from app.services.reward_service import RewardService, RewardSpec


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


_CAPTCHA_GLYPHS = {
    "0": ("11111", "10001", "10001", "10001", "10001", "10001", "11111"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("11111", "00001", "00001", "11111", "10000", "10000", "11111"),
    "3": ("11111", "00001", "00001", "11111", "00001", "00001", "11111"),
    "4": ("10001", "10001", "10001", "11111", "00001", "00001", "00001"),
    "5": ("11111", "10000", "10000", "11111", "00001", "00001", "11111"),
    "6": ("11111", "10000", "10000", "11111", "10001", "10001", "11111"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("11111", "10001", "10001", "11111", "10001", "10001", "11111"),
    "9": ("11111", "10001", "10001", "11111", "00001", "00001", "11111"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "−": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "×": ("10001", "01010", "00100", "00100", "00100", "01010", "10001"),
    "=": ("00000", "11111", "00000", "00000", "11111", "00000", "00000"),
    "؟": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    " ": ("00000",) * 7,
}


def _png_captcha(problem: str) -> bytes:
    """Render the whole arithmetic problem as a compact, high-contrast PNG."""
    scale = 6
    width = len(problem) * 6 * scale + 24
    height = 7 * scale + 24
    background = b"\x13\x22\x34"
    foreground = b"\xf3\xf8\xff"
    rows = [bytearray(b"\x00" + background * width) for _ in range(height)]
    for index, char in enumerate(problem):
        glyph = _CAPTCHA_GLYPHS[char]
        for gy, line in enumerate(glyph):
            for gx, bit in enumerate(line):
                if bit != "1":
                    continue
                start_x = 12 + (index * 6 + gx) * scale
                start_y = 12 + gy * scale
                for y in range(start_y, start_y + scale):
                    offset = 1 + start_x * 3
                    rows[y][offset : offset + scale * 3] = foreground * scale

    def chunk(kind: bytes, value: bytes) -> bytes:
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)
        )

    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


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
        problem = f"{left} {operation} {right} = ؟"
        return problem, _png_captcha(problem), str(result)

    @staticmethod
    def box_captcha() -> tuple[bytes, str, tuple[str, str, str]]:
        return make_letter_captcha()

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
