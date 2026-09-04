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
from app.services.reward_service import RewardService, RewardSpec


class ChanceError(RuntimeError):
    pass


class AlreadyClaimed(ChanceError):
    pass


class WrongCaptcha(ChanceError):
    pass


class BoxExpired(ChanceError):
    pass


def _png_captcha(answer: str) -> bytes:
    # Tiny dependency-free PNG renderer: 5x7 bitmap digits, scaled 8x.
    glyphs = {
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
    }
    scale, width, height = 8, len(answer) * 48 + 24, 80
    rows = []
    for y in range(height):
        # PNG scanline filter byte: 0 means "no filter". Values such as 255
        # make Telegram reject the generated image as an invalid PNG.
        row = bytearray([0])
        for x in range(width):
            row.extend((255, 255, 255))
        rows.append(row)
    for index, char in enumerate(answer):
        glyph = glyphs[char]
        for gy, line in enumerate(glyph):
            for gx, bit in enumerate(line):
                if bit == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            x = 12 + index * 48 + gx * scale + sx
                            y = 12 + gy * scale + sy
                            if y < height and x < width:
                                pos = 1 + x * 3
                                rows[y][pos:pos + 3] = b"\x20\x20\x20"
    raw = b"".join(rows)
    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class ChanceService:
    def __init__(self, reward_service: RewardService | None = None) -> None:
        self.reward_service = reward_service or RewardService()

    @staticmethod
    def captcha() -> tuple[str, bytes, str]:
        answer = "".join(secrets.choice("0123456789") for _ in range(4))
        digest = hashlib.sha256(answer.encode()).hexdigest()
        return answer, _png_captcha(answer), digest

    async def create_box(self, session: AsyncSession, group_id: int, message_id: int, resource: ResourceType, amount: int, *, now: datetime | None = None) -> ChanceBox:
        if amount < 0:
            raise ValueError("chance box amount cannot be negative")
        now = now or datetime.now(UTC)
        box = ChanceBox(group_id=group_id, telegram_message_id=message_id, resource_type=resource, amount=amount, expires_at=now + timedelta(minutes=game_config.chance_box_rules.expiry_minutes))
        session.add(box)
        await session.flush()
        return box

    async def claim_box(self, session: AsyncSession, box_id: int, telegram_user_id: int) -> tuple[ChanceBox, bool]:
        result = await session.execute(select(ChanceBox).where(ChanceBox.id == box_id).with_for_update())
        box = result.scalar_one_or_none()
        if box is None or box.claimed_by_user_id is not None:
            raise AlreadyClaimed
        now = datetime.now(UTC)
        expires_at = box.expires_at if box.expires_at.tzinfo else box.expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            await session.delete(box)
            await session.flush()
            raise BoxExpired
        result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ChanceError("user is not registered")
        box.claimed_by_user_id = user.id
        box.claimed_at = datetime.now(UTC)
        await self.reward_service.grant(session, user_id=user.id, spec=RewardSpec(box.resource_type, box.amount), source="CHANCE_BOX", reference_type="CHANCE_BOX", reference_id=box.id)
        await session.flush()
        return box, True

    async def create_card(self, session: AsyncSession, user_id: int, resource: ResourceType, amount: int, answer: str) -> ChanceCard:
        card = ChanceCard(user_id=user_id, resource_type=resource, amount=amount, captcha_answer=answer, captcha_hash=hashlib.sha256(answer.encode()).hexdigest())
        session.add(card)
        await session.flush()
        return card

    async def claim_card(self, session: AsyncSession, card_id: int, user_id: int, answer: str) -> ChanceCard:
        result = await session.execute(select(ChanceCard).where(ChanceCard.id == card_id, ChanceCard.user_id == user_id).with_for_update())
        card = result.scalar_one_or_none()
        if card is None or card.is_claimed:
            raise AlreadyClaimed
        if not secrets.compare_digest(card.captcha_hash, hashlib.sha256(answer.strip().encode()).hexdigest()):
            raise WrongCaptcha
        card.is_claimed = True
        card.claimed_at = datetime.now(UTC)
        await self.reward_service.grant(session, user_id=user_id, spec=RewardSpec(card.resource_type, card.amount), source="CHANCE_CARD", reference_type="CHANCE_CARD", reference_id=card.id)
        await session.flush()
        return card
