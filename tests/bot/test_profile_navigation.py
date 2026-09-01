from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import profile
from app.repositories.profile import ProfileSnapshot


def profile_snapshot() -> ProfileSnapshot:
    user = SimpleNamespace(
        telegram_user_id=123,
        first_name="آرش",
        last_name="دلاور",
        username="hero",
        created_at=datetime(2025, 1, 2, tzinfo=UTC),
        level=4,
        resources=SimpleNamespace(coin=1200, diamond=35, banana=9),
        castle=SimpleNamespace(
            level=2,
            strength=150,
            defense=SimpleNamespace(defense_power=40),
        ),
    )
    return ProfileSnapshot(
        user=user,
        teachers_count=3,
        active_teachers_count=2,
        attacks_sent=10,
        successful_attacks=6,
        pending_attacks=1,
        attacks_received=4,
        damage_dealt=120,
        loot_coin=80,
        loot_diamond=5,
        loot_banana=2,
        answers_count=8,
        correct_answers=6,
        referrals_count=3,
    )


@pytest.mark.asyncio
async def test_profile_handler_shows_rich_live_stats(monkeypatch) -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=900),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        profile.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        profile.profile_service,
        "snapshot",
        AsyncMock(return_value=profile_snapshot()),
    )

    await profile.profile_handler(message, AsyncMock())

    text = message.answer.await_args.args[0]
    assert "آرش دلاور" in text
    assert "💎 الماس: ۳۵" in text
    assert "حمله‌های موفق: ۶" in text
    assert "دقت: ۷۵٪" in text
    assert message.answer.await_args.kwargs["reply_markup"].inline_keyboard
