from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import referral, start
from app.services.referral_service import SelfReferral


@pytest.mark.asyncio
async def test_referral_menu_shows_personal_link_and_count(monkeypatch):
    bot_user = SimpleNamespace(username="godofdars_bot")
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        bot=SimpleNamespace(me=AsyncMock(return_value=bot_user)),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        referral.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        referral.referral_service,
        "count",
        AsyncMock(return_value=3),
    )

    await referral.referral_handler(message, AsyncMock())

    text = message.answer.await_args.args[0]
    assert "https://t.me/godofdars_bot?start=ref_7" in text
    assert "تعداد دعوت‌های ثبت‌شده: 3" in text
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].url.startswith("https://t.me/share/url")


@pytest.mark.asyncio
async def test_start_payload_applies_referral_before_showing_menu(monkeypatch):
    target = SimpleNamespace(answer=AsyncMock())
    telegram_user = SimpleNamespace(id=100, first_name="new")
    created_user = SimpleNamespace(id=200, is_active=True)
    monkeypatch.setattr(
        start.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=created_user),
    )
    monkeypatch.setattr(start.referral_service, "parse_payload", lambda value: 7)
    apply = AsyncMock()
    monkeypatch.setattr(start.referral_service, "apply", apply)
    session = AsyncMock()

    assert await start._initialize_and_show_menu(
        target=target,
        telegram_user=telegram_user,
        session=session,
        referral_payload="ref_7",
    )

    apply.assert_awaited_once_with(
        session,
        referred_user_id=created_user.id,
        referrer_id=7,
    )


@pytest.mark.asyncio
async def test_start_with_own_referral_link_shows_funny_notice(monkeypatch):
    target = SimpleNamespace(answer=AsyncMock())
    telegram_user = SimpleNamespace(id=100, first_name="self")
    created_user = SimpleNamespace(id=7, is_active=True)
    monkeypatch.setattr(
        start.user_service,
        "get_or_create_from_telegram",
        AsyncMock(return_value=created_user),
    )
    monkeypatch.setattr(start.referral_service, "parse_payload", lambda value: 7)
    monkeypatch.setattr(
        start.referral_service,
        "apply",
        AsyncMock(side_effect=SelfReferral),
    )

    await start._initialize_and_show_menu(
        target=target,
        telegram_user=telegram_user,
        session=AsyncMock(),
        referral_payload="ref_7",
    )

    assert any("خودتو دعوت" in call.args[0] for call in target.answer.await_args_list)
