from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.banners import archer_midway_banner
from app.bot.keyboards.school import school_keyboard, school_knights_keyboard
from app.bot.knight_banners import school_overview
from app.services.knight_service import KnightService


def _knight(*, hp: int = 30, equipped: bool = True):
    return SimpleNamespace(
        id=4,
        level=1,
        current_hp=hp,
        is_equipped=equipped,
        knight=SimpleNamespace(
            name="نگهبان",
            power=8,
            max_hp=30,
            upgrade_price=10,
            emoji=None,
            sticker="sticker-id",
        ),
    )


@pytest.mark.asyncio
async def test_knight_strikes_without_ammunition_and_loses_health() -> None:
    service = KnightService()
    owned = _knight()
    service.active = AsyncMock(return_value=owned)

    first = await service.strike(object(), 1, 80, 80, incoming_power=20)
    second = await service.strike(object(), 1, 80, 80, incoming_power=20)

    assert first is not None and second is not None
    assert first.damage == second.damage == 8
    assert first.reduction == second.reduction == 16
    assert first.arrow_name == "شمشیر"
    assert owned.current_hp == 20
    assert await service.reduction(object(), 1) == 16


@pytest.mark.asyncio
async def test_only_one_guard_is_equipped() -> None:
    service = KnightService()
    archer = SimpleNamespace(is_equipped=True)
    knight = _knight(equipped=False)
    session = SimpleNamespace(scalar=AsyncMock(return_value=archer), flush=AsyncMock())
    service._buyer = AsyncMock(return_value=(object(), object()))
    service.owned = AsyncMock(return_value=knight)

    await service.equip(session, 1, "knight")
    assert knight.is_equipped and not archer.is_equipped
    await service.equip(session, 1, "archer")
    assert archer.is_equipped and not knight.is_equipped


def test_knight_school_and_attack_banners_use_requested_emojis() -> None:
    school = school_keyboard()
    assert any(
        button.icon_custom_emoji_id == "5372804525935567057"
        for row in school.inline_keyboard
        for button in row
    )
    overview = school_overview(_knight())
    assert "tg://emoji?id=5825961702088254236" in overview
    assert "16٪" in overview
    owned = _knight()
    owned.knight.emoji = "1234567890123456789"
    assert "tg://emoji?id=1234567890123456789" in school_overview(owned)
    controls = school_knights_keyboard(_knight(equipped=False))
    assert controls.inline_keyboard[0][0].callback_data == "archer_shop:equip_knight:0"
    assert all(
        "knight_heal" not in button.callback_data
        for row in school_knights_keyboard(_knight(hp=10)).inline_keyboard
        for button in row
    )
    midway = archer_midway_banner(1, "دبیر", "نگهبان", None, 8, knight=True)
    assert "شوالیه" in midway and "tg://emoji?id=5825961702088254236" in midway
    death = archer_midway_banner(
        1, "دبیر", "نگهبان", None, 8, knight=True, knight_died=True
    )
    assert "از مدرسه حذف شد" in death
