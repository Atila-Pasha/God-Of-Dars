import hashlib
import struct
import zlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.chance_banners import chance_box_banner, chance_card_banner
from app.core.enums import ResourceType
from app.core.game_logic import game_config
from app.services.chance_service import (
    AlreadyClaimed,
    CardExpired,
    ChanceService,
    WrongCaptcha,
    _png_captcha,
)


def test_math_captcha_has_the_expected_answer() -> None:
    for _ in range(100):
        problem, image, answer = ChanceService.captcha()
        left, operator, right, _equals, _question = problem.split()
        numbers = int(left), int(right)
        if operator == "+":
            expected = numbers[0] + numbers[1]
        elif operator == "−":
            expected = numbers[0] - numbers[1]
        else:
            expected = numbers[0] * numbers[1]
        assert answer == str(expected)
        assert expected >= 0
        assert image.startswith(b"\x89PNG\r\n\x1a\n")


def test_math_problem_is_drawn_into_the_png() -> None:
    image = _png_captcha("7 × 3 = ؟")
    width, height = struct.unpack(">II", image[16:24])
    idat_offset = image.index(b"IDAT") + 4
    idat_size = struct.unpack(">I", image[idat_offset - 8 : idat_offset - 4])[0]
    raw = zlib.decompress(image[idat_offset : idat_offset + idat_size])

    assert width > 250
    assert height > 50
    assert len(raw) == height * (1 + width * 3)
    assert b"\xf3\xf8\xff" in raw  # visible white glyph pixels
    assert b"\x13\x22\x34" in raw  # contrasting dark background
    assert image != _png_captcha("7 + 3 = ؟")


def test_chance_banners_use_requested_icons_and_spoilers() -> None:
    assert game_config.chance_box_rules.expiry_minutes == 5
    box = chance_box_banner(5)
    card = chance_card_banner(datetime(2026, 10, 8, 12, 37, tzinfo=UTC))

    assert "tg://emoji?id=5825832256068918886" in box
    assert "tg://emoji?id=5086915529730426905" in box
    assert "||5 دقیقه||" in box
    assert "tg://emoji?id=5267300544094948794" in card
    assert "tg://emoji?id=5825746176334373354" in card
    assert "||16:07||" in card
    assert "7 × 3" not in card


@pytest.mark.asyncio
async def test_wrong_card_answer_consumes_the_only_attempt() -> None:
    card = SimpleNamespace(
        id=1,
        is_claimed=False,
        created_at=datetime.now(UTC),
        captcha_hash=hashlib.sha256(b"21").hexdigest(),
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: card)
        ),
        flush=AsyncMock(),
    )
    reward_service = SimpleNamespace(grant=AsyncMock())
    service = ChanceService(reward_service)

    with pytest.raises(WrongCaptcha):
        await service.claim_card(session, card.id, 9, "22")

    assert card.is_claimed is True
    session.flush.assert_awaited_once()
    reward_service.grant.assert_not_awaited()
    with pytest.raises(AlreadyClaimed):
        await service.claim_card(session, card.id, 9, "21")


@pytest.mark.asyncio
async def test_expired_card_cannot_grant_reward() -> None:
    card = SimpleNamespace(
        id=1,
        is_claimed=False,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: card))
    )
    reward_service = SimpleNamespace(grant=AsyncMock())

    with pytest.raises(CardExpired):
        await ChanceService(reward_service).claim_card(session, 1, 9, "21")

    reward_service.grant.assert_not_awaited()


@pytest.mark.asyncio
async def test_correct_card_answer_accepts_persian_digits_and_grants_once() -> None:
    card = SimpleNamespace(
        id=2,
        is_claimed=False,
        claimed_at=None,
        created_at=datetime.now(UTC),
        captcha_hash=hashlib.sha256(b"21").hexdigest(),
        resource_type=ResourceType.BANANA,
        amount=10,
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: card)
        ),
        flush=AsyncMock(),
    )
    reward_service = SimpleNamespace(grant=AsyncMock())

    result = await ChanceService(reward_service).claim_card(session, 2, 9, "۲۱")

    assert result is card
    assert card.is_claimed is True
    assert card.claimed_at is not None
    reward_service.grant.assert_awaited_once()
