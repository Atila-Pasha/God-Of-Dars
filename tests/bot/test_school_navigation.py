from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import (
    CastleCallback,
    ConfirmationCallback,
    HospitalCallback,
    TeacherCallback,
)
from app.bot.handlers import school
from app.services.recovery_service import HospitalSnapshot
from app.services.school_errors import CastleNeedsRepair


def callback() -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_hospital_banner_shows_time_and_bed_emoji_without_upgrade_details(
    monkeypatch,
) -> None:
    target = callback()
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=10)))
    monkeypatch.setattr(school.hospital_service, "patients", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        school.hospital_service,
        "snapshot",
        AsyncMock(
            return_value=HospitalSnapshot(
                level=1,
                capacity=1,
                occupied=0,
                speed_percent=100,
                recovery_minutes=240,
                next_capacity=2,
                next_speed_percent=125,
                next_recovery_minutes=192,
                upgrade_cost=120,
                required_player_level=3,
                player_level=1,
            )
        ),
    )
    send = AsyncMock()
    monkeypatch.setattr(school, "_send_or_edit", send)

    await school._hospital_view(target, AsyncMock())

    banner = send.await_args.args[1]
    assert "5275983061001977055" in banner
    assert "4 ساعت" in banner
    assert "ارتقای بعدی" not in banner
    assert "120" not in banner
    markup = send.await_args.kwargs["reply_markup"]
    assert any(
        button.text == "ارتقای بیمارستان"
        for row in markup.inline_keyboard
        for button in row
    )


def test_hospital_duration_uses_hours_and_minutes() -> None:
    assert school._duration_text(192) == "3 ساعت و 12 دقیقه"
    assert school._duration_text(30) == "30 دقیقه"


@pytest.mark.asyncio
async def test_locked_hospital_upgrade_still_shows_time_change(monkeypatch) -> None:
    target = callback()
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=10)))
    monkeypatch.setattr(
        school.hospital_service,
        "snapshot",
        AsyncMock(
            return_value=HospitalSnapshot(
                level=1,
                capacity=1,
                occupied=0,
                speed_percent=100,
                recovery_minutes=240,
                next_capacity=2,
                next_speed_percent=125,
                next_recovery_minutes=192,
                upgrade_cost=120,
                required_player_level=3,
                player_level=1,
            )
        ),
    )
    send = AsyncMock()
    monkeypatch.setattr(school, "_send_or_edit", send)

    await school.hospital_callback_handler(
        target, HospitalCallback(action="upgrade", teacher_id=0), AsyncMock()
    )

    banner = send.await_args.args[1]
    assert "4 ساعت" in banner
    assert "3 ساعت و 12 دقیقه" in banner
    assert "5275983061001977055" in banner
    assert "هنوز برای سطح شما باز نشده" in banner.replace("\\", "")
    markup = send.await_args.kwargs["reply_markup"]
    assert len(markup.inline_keyboard[0]) == 1


@pytest.mark.asyncio
async def test_castle_back_returns_to_school_menu(monkeypatch) -> None:
    target = callback()
    session = AsyncMock()
    school_view = AsyncMock()
    castle_view = AsyncMock()
    monkeypatch.setattr(school, "_school_view", school_view)
    monkeypatch.setattr(school, "_castle_view", castle_view)

    await school.castle_callback_handler(
        target,
        CastleCallback(action="back"),
        session,
    )

    school_view.assert_awaited_once_with(target, session)
    castle_view.assert_not_awaited()
    target.answer.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_damaged_castle_upgrade_button_explains_repair_first(monkeypatch) -> None:
    target = callback()
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=10)))
    monkeypatch.setattr(
        school.castle_service,
        "snapshot",
        AsyncMock(return_value=SimpleNamespace(level=1, strength=0, defense_power=25)),
    )
    send = AsyncMock()
    monkeypatch.setattr(school, "_send_or_edit", send)

    await school.castle_callback_handler(
        target, CastleCallback(action="upgrade"), AsyncMock()
    )

    target.answer.assert_awaited_once_with(
        "اول دژ را تعمیر کن، بعد ارتقا بده.", show_alert=True
    )
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_upgrade_confirmation_rechecks_damage_before_spending(
    monkeypatch,
) -> None:
    target = callback()
    session = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=10)))
    monkeypatch.setattr(
        school.castle_service,
        "upgrade",
        AsyncMock(side_effect=CastleNeedsRepair),
    )
    castle_view = AsyncMock()
    monkeypatch.setattr(school, "_castle_view", castle_view)

    await school.confirmation_callback_handler(
        target,
        ConfirmationCallback(action="castle_upgrade", target_id=0, decision="confirm"),
        session,
    )

    session.rollback.assert_awaited_once()
    castle_view.assert_awaited_once_with(target, session)
    target.answer.assert_awaited_once_with(
        "اول دژ را تعمیر کن، بعد ارتقا بده.", show_alert=True
    )


@pytest.mark.asyncio
async def test_hospital_back_returns_to_school_menu(monkeypatch) -> None:
    target = callback()
    session = AsyncMock()
    user = SimpleNamespace(id=10)
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=user))
    school_view = AsyncMock()
    hospital_view = AsyncMock()
    monkeypatch.setattr(school, "_school_view", school_view)
    monkeypatch.setattr(school, "_hospital_view", hospital_view)

    await school.hospital_callback_handler(
        target,
        HospitalCallback(action="back", teacher_id=0),
        session,
    )

    school_view.assert_awaited_once_with(target, session)
    hospital_view.assert_not_awaited()
    target.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_teacher_list_back_returns_to_school_menu(monkeypatch) -> None:
    target = callback()
    session = AsyncMock()
    user = SimpleNamespace(id=10)
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=user))
    school_view = AsyncMock()
    teachers_view = AsyncMock()
    monkeypatch.setattr(school, "_school_view", school_view)
    monkeypatch.setattr(school, "_teachers_view", teachers_view)

    await school.teacher_callback_handler(
        target,
        TeacherCallback(action="back_school", teacher_id=0),
        session,
    )

    school_view.assert_awaited_once_with(target, session)
    teachers_view.assert_not_awaited()
    target.answer.assert_awaited_once_with()
