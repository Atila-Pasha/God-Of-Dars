from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import LibraryCallback, LibraryGuardCallback
from app.bot.handlers import library
from app.bot.middlewares.group import GroupAccessMiddleware
from app.core.enums import ResourceType


def guard(kind: str, *, name: str | None = None):
    return SimpleNamespace(
        id=11 if kind == "archer" else 12,
        name=name or ("آرش" if kind == "archer" else "رستم"),
        power=20,
        max_hp=150,
        unlock_level=3,
        purchase_price=250,
        purchase_resource=ResourceType.COIN,
        upgrade_price=40,
        emoji=None,
        description="دفاع *ویژه*",
        is_active=True,
    )


@pytest.mark.parametrize("kind", ["archer", "knight"])
def test_guard_detail_contains_buying_and_combat_information(kind) -> None:
    text = library._guard_detail_content(guard(kind), kind=kind)
    assert "250 طلا" in text
    assert "40 الماس" in text
    assert "3" in text
    assert "دفاع \\*ویژه\\*" in text
    assert "5 ساعت" in text
    if kind == "knight":
        assert "150 HP" in text
        assert "40٪" in text
    else:
        assert "100 HP" in text
        assert "هر دبیر مهاجم" in text


def test_archer_can_be_found_without_catalog_note() -> None:
    item = guard("archer", name="محسنی (آزمایشی)")
    assert library._catalog_matches([item], "محسنی", kind="archer") == [item]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["archer", "knight"])
async def test_library_guard_list_detail_and_back(monkeypatch, kind) -> None:
    item = guard(kind)
    monkeypatch.setattr(
        library.archer_service if kind == "archer" else library.knight_service,
        "catalog",
        AsyncMock(return_value=[item]),
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    session = AsyncMock()
    await library.library_callback_handler(
        callback,
        LibraryCallback(action="archers" if kind == "archer" else "knights"),
        session,
        AsyncMock(),
    )
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == f"library_guard:view:{kind}:{item.id}"

    await library.library_guard_callback(
        callback,
        LibraryGuardCallback(action="view", kind=kind, item_id=item.id),
        session,
    )
    assert item.name in callback.message.edit_text.await_args.args[0]
    back = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert back.inline_keyboard[0][0].callback_data == f"library_guard:back:{kind}:0"

    await library.library_guard_callback(
        callback, LibraryGuardCallback(action="back", kind=kind), session
    )
    assert "دانشنامه" in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_group_introduces_shield_archer_and_knight(monkeypatch) -> None:
    shield = SimpleNamespace(
        id=7,
        name="سپر زنگ تفریح",
        purchase_resource=ResourceType.COIN,
        purchase_price=120,
        unlock_level=1,
        duration_minutes=30,
        reduction_percent=10,
        flat_absorption=5,
        daily_limit=2,
        description="محافظت",
    )
    monkeypatch.setattr(library.teacher_service, "public_teachers", AsyncMock(return_value=[]))
    monkeypatch.setattr(library.shield_service, "catalog", AsyncMock(return_value=[shield]))
    monkeypatch.setattr(library.archer_service, "catalog", AsyncMock(return_value=[guard("archer")]))
    monkeypatch.setattr(library.knight_service, "catalog", AsyncMock(return_value=[guard("knight")]))
    message = SimpleNamespace(text="", answer=AsyncMock())

    for command, expected in (
        ("معرفی سپر زنگ تفریح", "محافظت"),
        ("معرفی زنگ تفریح", "محافظت"),
        ("معرفی کماندار آرش", "پروندهٔ کماندار"),
        ("معرفی آرش", "پروندهٔ کماندار"),
        ("معرفی شوالیه رستم", "پروندهٔ شوالیه"),
        ("معرفی رستم", "پروندهٔ شوالیه"),
        ("معرفی شوالیه‌ها", "رستم"),
        ("معرفی سپر ها", "سپر زنگ تفریح"),
    ):
        assert GroupAccessMiddleware._message_is_allowed(SimpleNamespace(text=command))
        message.text = command
        await library.group_teacher_introduction(message, AsyncMock())
        assert expected in message.answer.await_args.args[0]
