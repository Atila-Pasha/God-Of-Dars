from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import school
from app.bot.keyboards.mine import mine_keyboard


def test_school_capacity_bar_uses_green_premium_pieces() -> None:
    bar = school._progress_bar(2, 30)

    assert "tg://emoji?id=594" in bar
    assert "tg://emoji?id=593" in bar
    assert "█" not in bar and "░" not in bar
    assert bar.startswith("\u2066") and bar.endswith("\u2069")


@pytest.mark.asyncio
async def test_empty_teacher_section_escapes_markdown_and_keeps_premium_bar(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        school, "_user", AsyncMock(return_value=SimpleNamespace(id=1, level=1))
    )
    monkeypatch.setattr(
        school.teacher_service,
        "capacity",
        AsyncMock(return_value=SimpleNamespace(owned=0, available=2, maximum=30)),
    )
    monkeypatch.setattr(school.teacher_service, "owned", AsyncMock(return_value=[]))
    monkeypatch.setattr(school.teacher_service, "catalog", AsyncMock(return_value=[]))
    send = AsyncMock()
    monkeypatch.setattr(school, "_send_or_edit", send)

    await school._teachers_view(
        SimpleNamespace(from_user=SimpleNamespace(id=42)), AsyncMock()
    )

    text = send.await_args.args[1]
    assert "اضافه نشده است\\." in text
    assert "tg://emoji?id=593" in text
    assert "█" not in text


def test_mine_shows_independent_collection_buttons() -> None:
    markup = mine_keyboard(can_upgrade=False)
    buttons = markup.inline_keyboard[0]

    assert [button.text for button in buttons] == ["برداشت طلا", "برداشت الماس"]
    assert [button.callback_data for button in buttons] == [
        "mine:collect_coin",
        "mine:collect_diamond",
    ]
