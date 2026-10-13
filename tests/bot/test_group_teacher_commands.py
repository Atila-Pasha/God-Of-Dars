from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import school
from app.core.enums import TeacherStatus
from app.services.school_errors import InvalidTeacherState


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


@pytest.mark.asyncio
async def test_group_discharge_uses_hospital_service(monkeypatch) -> None:
    message = _message("ترخیص فراهانی")
    owned = SimpleNamespace(id=5, teacher=SimpleNamespace(id=9, name="پارسا فراهانی"))
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "owned", AsyncMock(return_value=[owned])
    )
    discharge = AsyncMock(return_value=owned)
    monkeypatch.setattr(school.hospital_service, "discharge", discharge)
    session = AsyncMock()

    await school.group_discharge_teacher(message, session)

    discharge.assert_awaited_once_with(session, 1, 5)
    assert "ترخیص شد" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_group_discharge_rejects_teacher_not_ready(monkeypatch) -> None:
    message = _message("ترخیص فراهانی")
    owned = SimpleNamespace(id=5, teacher=SimpleNamespace(id=9, name="پارسا فراهانی"))
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "owned", AsyncMock(return_value=[owned])
    )
    monkeypatch.setattr(
        school.hospital_service,
        "discharge",
        AsyncMock(side_effect=InvalidTeacherState),
    )
    session = AsyncMock()

    await school.group_discharge_teacher(message, session)

    session.rollback.assert_awaited_once()
    assert "هنوز آمادهٔ ترخیص نیست" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_group_discharge_requires_teacher_name() -> None:
    message = _message("ترخیص")

    await school.group_discharge_teacher(message, AsyncMock())

    assert "ترخیص {اسم دبیر}" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_group_teacher_status_lists_owned_teachers_and_recovery(
    monkeypatch,
) -> None:
    message = _message("وضعیت دبیر ها")
    now = datetime.now(UTC)
    owned = [
        SimpleNamespace(
            level=2,
            current_hp=80,
            status=TeacherStatus.ACTIVE,
            teacher=SimpleNamespace(name="پارسا فراهانی", emoji="🔥", max_hp=100),
            recoveries=[],
        ),
        SimpleNamespace(
            level=1,
            current_hp=35,
            status=TeacherStatus.RECOVERING,
            teacher=SimpleNamespace(name="احمدی", emoji="123", max_hp=90),
            recoveries=[
                SimpleNamespace(
                    completed_at=None,
                    recovery_end_at=now + timedelta(minutes=12),
                )
            ],
        ),
    ]
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    catalog = AsyncMock(return_value=owned)
    monkeypatch.setattr(school.teacher_service, "owned", catalog)

    await school.group_teacher_status(message, AsyncMock())

    catalog.assert_awaited_once()
    output = message.answer.await_args.args[0]
    assert "پارسا فراهانی" in output and "احمدی" in output
    assert "جان: 80 / 100" in output
    assert "فعال" in output and "در حال درمان" in output
    assert "زمان باقی" in output
    assert "tg://emoji?id=" in output
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_group_teacher_status_shows_discharge_command_when_ready(
    monkeypatch,
) -> None:
    message = _message("وضعیت دبیرها")
    owned = SimpleNamespace(
        level=1,
        current_hp=35,
        status=TeacherStatus.RECOVERING,
        teacher=SimpleNamespace(name="احمدی", emoji=None, max_hp=90),
        recoveries=[
            SimpleNamespace(
                completed_at=None,
                recovery_end_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        ],
    )
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "owned", AsyncMock(return_value=[owned])
    )

    await school.group_teacher_status(message, AsyncMock())

    output = message.answer.await_args.args[0]
    assert "در انتظار ترخیص" in output
    assert "ترخیص احمدی" in output


@pytest.mark.asyncio
async def test_group_teacher_status_handles_empty_team(monkeypatch) -> None:
    message = _message("وضعیت دبیر ها")
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(school.teacher_service, "owned", AsyncMock(return_value=[]))

    await school.group_teacher_status(message, AsyncMock())

    assert "هنوز دبیری" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_group_buyable_teachers_lists_only_name_ability_and_teacher_emoji(
    monkeypatch,
) -> None:
    message = _message("چه دبیر هایی رو میتونم بخرم؟")
    teachers = [
        SimpleNamespace(name="فراهانی", emoji="🔥", ability_text="ضربه *ویژه*"),
        SimpleNamespace(name="احمدی", emoji="🦉", ability_text=None),
    ]
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    catalog = AsyncMock(return_value=teachers)
    monkeypatch.setattr(school.teacher_service, "buyable_catalog", catalog)

    await school.group_buyable_teachers(message, AsyncMock())

    catalog.assert_awaited_once()
    output = message.answer.await_args.args[0]
    assert "فراهانی" in output and "احمدی" in output
    assert "ضربه \\*ویژه\\*" in output
    assert "ثبت نشده" in output
    assert "tg://emoji?id=" in output
    assert "قیمت" not in output and "ظرفیت" not in output
    assert message.answer.await_args.kwargs["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_group_buyable_teachers_empty(monkeypatch) -> None:
    message = _message("دبیر های مجاز")
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(
        school.teacher_service, "buyable_catalog", AsyncMock(return_value=[])
    )

    await school.group_buyable_teachers(message, AsyncMock())

    assert "دبیری برای خرید نداری" in message.answer.await_args.args[0]
