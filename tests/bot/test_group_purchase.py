from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import ConfirmationCallback
from app.bot.handlers import buffet, school
from app.core.enums import ResourceType


def group_message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=42),
        chat=SimpleNamespace(type="supergroup"),
        message_id=100,
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_group_teacher_purchase_opens_confirmation_without_private_menu(
    monkeypatch,
) -> None:
    message = group_message("خرید فراهانی")
    teacher = SimpleNamespace(id=17, name="پارسا فراهانی")
    monkeypatch.setattr(
        buffet.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(level=10)),
    )
    monkeypatch.setattr(
        buffet.teacher_service,
        "public_teachers",
        AsyncMock(return_value=[teacher]),
    )
    monkeypatch.setattr(buffet, "purchase_banner", lambda item: item.name)
    shield_catalog = AsyncMock()
    monkeypatch.setattr(buffet.shield_service, "catalog", shield_catalog)

    await buffet.group_purchase_message(message, AsyncMock())

    assert message.answer.await_args.args[0] == "پارسا فراهانی"
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data.startswith(
        "confirm:teacher_buy:17"
    )
    shield_catalog.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_shield_purchase_uses_shield_confirmation(monkeypatch) -> None:
    message = group_message("خرید سپر زنگ تفریح")
    shield = SimpleNamespace(
        id=1,
        name="سپر زنگ تفریح",
        purchase_price=120,
        purchase_resource=ResourceType.COIN,
        duration_minutes=30,
    )
    monkeypatch.setattr(
        buffet.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(level=10)),
    )
    monkeypatch.setattr(
        buffet.shield_service,
        "catalog",
        AsyncMock(return_value=[shield]),
    )
    teacher_catalog = AsyncMock()
    monkeypatch.setattr(buffet.teacher_service, "public_teachers", teacher_catalog)

    await buffet.group_purchase_message(message, AsyncMock())

    markup = message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == "shield_purchase:confirm:1"
    teacher_catalog.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_purchase_menu_words_only_show_command_format() -> None:
    shield_message = group_message("خرید سپر")
    teacher_message = group_message("خرید دبیر")

    await buffet.buffet_shields_message(
        shield_message, AsyncMock(), SimpleNamespace(clear=AsyncMock())
    )
    await buffet.buffet_teachers_message(
        teacher_message, AsyncMock(), SimpleNamespace(clear=AsyncMock())
    )

    assert "خرید سپر {اسم سپر}" in shield_message.answer.await_args.args[0]
    assert "خرید {اسم دبیر}" in teacher_message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_confirmed_group_teacher_purchase_sends_no_catalog(monkeypatch) -> None:
    monkeypatch.setattr(school, "Message", SimpleNamespace)
    source = SimpleNamespace(
        message_id=100,
        from_user=SimpleNamespace(id=42, is_bot=False),
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(type="supergroup"),
        reply_to_message=source,
        answer=AsyncMock(),
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42), message=message, answer=AsyncMock()
    )
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(school, "_user", AsyncMock(return_value=SimpleNamespace(id=5)))
    monkeypatch.setattr(
        school.teacher_service,
        "buy",
        AsyncMock(
            return_value=SimpleNamespace(teacher=SimpleNamespace(name="پارسا فراهانی"))
        ),
    )
    delete_prompt = AsyncMock()
    monkeypatch.setattr(school, "_delete_group_purchase_prompt", delete_prompt)
    private_shop = AsyncMock()
    monkeypatch.setattr(buffet, "_teacher_shop_view", private_shop)

    await school.confirmation_callback_handler(
        callback,
        ConfirmationCallback(
            action="teacher_buy", target_id=17, decision="confirm", origin="buffet"
        ),
        session,
    )

    session.commit.assert_awaited_once()
    delete_prompt.assert_awaited_once()
    private_shop.assert_not_awaited()
    assert "خریداری شد" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_to_message_id"] == 100
