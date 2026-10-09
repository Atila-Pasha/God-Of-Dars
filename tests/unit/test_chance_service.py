import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.bot.chance_banners import chance_box_banner, chance_card_banner
from app.bot.relative_time import remaining_time
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
    image = Image.open(BytesIO(_png_captcha("7 × 3 = ?"))).convert("RGB")
    assert image.size == (760, 260)
    assert image.getpixel((0, 0)) == (16, 29, 50)
    assert image.getpixel((380, 35)) == (247, 249, 252)
    ink = Image.new("1", image.size)
    raw = image.tobytes()
    ink.putdata(
        [
            raw[offset : offset + 3] == b"\x17\x2b\x44"
            for offset in range(0, len(raw), 3)
        ]
    )
    left, top, right, bottom = ink.getbbox()
    assert abs((left + right) / 2 - image.width / 2) <= 2
    assert abs((top + bottom) / 2 - image.height / 2) <= 2
    assert _png_captcha("7 × 3 = ?") != _png_captcha("7 + 3 = ?")


def test_symbol_box_has_one_sword_and_nine_matching_positions() -> None:
    for _ in range(30):
        image, answer, choices = ChanceService.box_captcha()
        picture = Image.open(BytesIO(image)).convert("RGB")
        assert picture.size == (720, 720)
        assert choices == tuple("123456789")
        assert answer in choices
        gold_tiles = []
        for index in range(9):
            x, y = 48 + (index % 3) * 218, 48 + (index // 3) * 218
            tile = picture.crop((x, y, x + 188, y + 188))
            if b"\xe8\xba\x5a" in tile.tobytes():
                gold_tiles.append(str(index + 1))
        assert gold_tiles == [answer]


def test_chance_banners_use_requested_icons_and_spoilers() -> None:
    assert game_config.chance_box_rules.expiry_minutes == 5
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    box = chance_box_banner(expires_at)
    card = chance_card_banner(expires_at)

    assert "tg://emoji?id=5825832256068918886" in box
    assert "نماد متفاوت" in box
    assert "tg://emoji?id=5086915529730426905" in box
    assert f"tg://time?unix={int(expires_at.timestamp())}&format=r" in box
    assert "tg://emoji?id=5267300544094948794" in card
    assert "معادله رو حل کن" in card
    assert "tg://emoji?id=5825746176334373354" in card
    assert "format=r)||" in card
    assert "7 × 3" not in card


def test_relative_time_uses_a_live_telegram_entity_inside_spoiler() -> None:
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)

    text = remaining_time(now + timedelta(minutes=5), now=now)

    assert text == "||![5 دقیقه](tg://time?unix=1791461100&format=r)||"


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
