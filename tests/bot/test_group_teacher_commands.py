from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import school


def _message(text: str):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_group_sell_preserves_full_hp_rule(monkeypatch) -> None:
    message = _message("فروش فراهانی")
    owned = SimpleNamespace(
        id=5,
        current_hp=50,
        teacher=SimpleNamespace(id=9, name="پارسا فراهانی", max_hp=100),
    )
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "owned", AsyncMock(return_value=[owned])
    )
    sell = AsyncMock()
    monkeypatch.setattr(school.teacher_service, "sell", sell)

    await school.group_sell_teacher(message, AsyncMock())

    sell.assert_not_awaited()
    assert "کاملاً درمان" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_group_sell_uses_service_and_premium_emoji(monkeypatch) -> None:
    message = _message("فروش فراهانی")
    owned = SimpleNamespace(
        id=5,
        current_hp=100,
        teacher=SimpleNamespace(id=9, name="پارسا فراهانی", max_hp=100),
    )
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "owned", AsyncMock(return_value=[owned])
    )
    sell = AsyncMock(return_value=50)
    monkeypatch.setattr(school.teacher_service, "sell", sell)

    await school.group_sell_teacher(message, AsyncMock())

    sell.assert_awaited_once()
    assert "tg://emoji?id=" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_group_heal_starts_standard_recovery(monkeypatch) -> None:
    message = _message("درمان فراهانی")
    owned = SimpleNamespace(id=5, teacher=SimpleNamespace(id=9, name="پارسا فراهانی"))
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "owned", AsyncMock(return_value=[owned])
    )
    begin = AsyncMock()
    monkeypatch.setattr(school.hospital_service, "begin_recovery", begin)

    await school.group_recover_teacher(message, AsyncMock())

    begin.assert_awaited_once()
    assert "آغاز شد" in message.answer.await_args.args[0]
