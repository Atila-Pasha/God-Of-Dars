from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import library
from app.bot.teacher_lookup import matching_teachers


def test_full_name_and_surname_resolve_the_same_teacher() -> None:
    farahani = SimpleNamespace(name="پارسا فراهانی")
    ghazati = SimpleNamespace(name="قضاتی")
    teachers = [farahani, ghazati]

    assert matching_teachers(teachers, "فراهانی") == [farahani]
    assert matching_teachers(teachers, "پارسا فراهانی") == [farahani]
    assert matching_teachers(teachers, "قضاتی") == [ghazati]
    assert matching_teachers(teachers, "امیر قضاتی") == [ghazati]


def test_ambiguous_surname_returns_all_matches() -> None:
    teachers = [
        SimpleNamespace(name="پارسا فراهانی"),
        SimpleNamespace(name="امیر فراهانی"),
    ]
    assert matching_teachers(teachers, "فراهانی") == teachers
    assert matching_teachers(teachers, "پارسا فراهانی") == teachers[:1]


@pytest.mark.asyncio
async def test_group_introduction_accepts_full_and_short_names(monkeypatch) -> None:
    teachers = [
        SimpleNamespace(name="پارسا فراهانی"),
        SimpleNamespace(name="قضاتی"),
    ]
    monkeypatch.setattr(
        library.teacher_service,
        "public_teachers",
        AsyncMock(return_value=teachers),
    )
    monkeypatch.setattr(
        library, "_teacher_detail_content", lambda teacher: teacher.name
    )
    message = SimpleNamespace(text="معرفی فراهانی", answer=AsyncMock())

    for command, expected in (
        ("معرفی فراهانی", "پارسا فراهانی"),
        ("معرفی پارسا فراهانی", "پارسا فراهانی"),
        ("معرفی قضاتی", "قضاتی"),
        ("معرفی امیر قضاتی", "قضاتی"),
    ):
        message.text = command
        await library.group_teacher_introduction(message, AsyncMock())
        assert message.answer.await_args.args[0] == expected
