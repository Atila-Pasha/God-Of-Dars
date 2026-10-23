import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import battle
from app.bot.rank_banners import (
    rank_profile_banner,
    rank_season_reward_banner,
    rank_status_banner,
)
from app.services.rank_service import TIERS, RankService, RankView


@pytest.mark.asyncio
async def test_rank_command_renders_all_supplied_premium_emojis_and_english_digits(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        battle.attack_service.users,
        "get_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=7, is_active=True)),
    )
    monkeypatch.setattr(
        RankService,
        "view",
        AsyncMock(return_value=RankView(601, TIERS[2], 4, 1, 16, 1001)),
    )
    message = SimpleNamespace(from_user=SimpleNamespace(id=70), answer=AsyncMock())

    await battle.rank_status_handler(message, SimpleNamespace())

    text = message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"
    for tier in TIERS:
        assert f"tg://emoji?id={tier.emoji_id}" in text
    assert "*601 جام*" in text
    assert "16 / 20" in text
    assert "0–200 جام" in text
    assert "2601\\+ جام" in text
    assert "400 جام" in text
    assert "00:00" in text
    assert "فصل ماهانه" in text
    assert "پاداش هر حمله" in text
    assert "\u2002\u2002" in text
    assert "\\|" in text
    assert not re.search(r"[۰-۹٠-٩]", text)


def test_compact_rank_and_season_reward_cards_use_english_digits() -> None:
    view = RankView(2800, TIERS[-1], 12, 3, 0, None)
    profile = rank_profile_banner(view)
    settlement = rank_season_reward_banner(TIERS[-1], 2800)

    assert "2800" in profile and "0 / 20" in profile
    assert "به بالاترین رنک" in profile
    assert "400" in settlement and "18" in settlement and "12" in settlement
    assert not re.search(r"[۰-۹٠-٩]", profile + settlement)


def test_rank_tier_ranges_are_contiguous() -> None:
    text = rank_status_banner(RankView(0, TIERS[0], 0, 0, 20, 201))
    for index, tier in enumerate(TIERS[:-1]):
        assert f"{tier.minimum}–{TIERS[index + 1].minimum - 1} جام" in text
