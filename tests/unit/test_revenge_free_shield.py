from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser

from app.bot.banners import revenge_prompt_banner
from app.bot.callbacks import RevengeCallback
from app.bot.handlers import battle
from app.bot.keyboards.revenge import revenge_keyboard
from app.core.enums import AttackStatus
from app.services.attack_service import AttackService
from app.services.school_errors import TargetProtectedByShield
from app.services.shield_service import ShieldService
from app.workers.attack_resolver import _award_free_shield


def test_revenge_buttons_have_requested_styles_and_sword() -> None:
    no, revenge = revenge_keyboard(42).inline_keyboard[0]
    assert (no.text, no.style) == ("نه", "success")
    assert (revenge.text, revenge.style) == ("انتقام", "danger")
    assert revenge.icon_custom_emoji_id == "5823192436024813346"
    assert "42" in revenge.callback_data


def test_revenge_prompt_starts_in_persian_with_attacker_name_inside_sentence() -> None:
    message = revenge_prompt_banner("Alex_7")
    assert message.startswith("*فرمانده تو از طرف Alex\\_7 مورد حمله قرار گرفتی")
    assert "می‌خوای انتقام بگیری یا نه؟" in message
    assert "\n" not in message


@pytest.mark.asyncio
async def test_fifth_resolved_attack_grants_exactly_one_hour_and_resets_count() -> None:
    defender = SimpleNamespace(attacks_since_free_shield=0, free_shield_until=None)
    session = SimpleNamespace(get=AsyncMock(return_value=defender))
    result = SimpleNamespace(
        attack=SimpleNamespace(target_id=12),
        blocked_by_shield=False,
        castle_damage=3,
        raid_damage=0,
    )
    for _ in range(4):
        assert not await _award_free_shield(session, result)
    start = datetime.now(UTC)
    assert await _award_free_shield(session, result)
    assert defender.attacks_since_free_shield == 0
    assert start + timedelta(hours=1) <= defender.free_shield_until
    assert defender.free_shield_until <= datetime.now(UTC) + timedelta(hours=1)


@pytest.mark.asyncio
async def test_blocked_attack_does_not_advance_free_shield_counter() -> None:
    defender = SimpleNamespace(attacks_since_free_shield=4, free_shield_until=None)
    session = SimpleNamespace(get=AsyncMock(return_value=defender))
    result = SimpleNamespace(
        attack=SimpleNamespace(target_id=12),
        blocked_by_shield=True,
        castle_damage=0,
        raid_damage=0,
    )
    assert not await _award_free_shield(session, result)
    assert defender.attacks_since_free_shield == 4
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_free_shield_blocks_even_when_castle_is_destroyed() -> None:
    service = AttackService()
    service.castles.get_by_user = AsyncMock(return_value=SimpleNamespace(strength=0))
    service.castle_service.shield_service.has_free_shield = AsyncMock(return_value=True)
    with pytest.raises(TargetProtectedByShield):
        await service._ensure_target_attackable(SimpleNamespace(), 12)


@pytest.mark.asyncio
async def test_free_shield_expires_at_its_deadline() -> None:
    now = datetime.now(UTC)
    session = SimpleNamespace(scalar=AsyncMock(return_value=now + timedelta(seconds=1)))
    shield = ShieldService()
    assert await shield.has_free_shield(session, 12, now=now)
    assert not await shield.has_free_shield(session, 12, now=now + timedelta(seconds=1))


@pytest.mark.asyncio
async def test_free_shield_absorbs_all_damage_without_a_purchased_shield() -> None:
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=datetime.now(UTC) + timedelta(minutes=30)),
        execute=AsyncMock(),
    )
    mitigation = await ShieldService().mitigate_attack(session, 12, 80)
    assert (mitigation.blocked_damage, mitigation.remaining_damage) == (80, 0)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_revenge_uses_original_attacker_and_checks_defender(
    monkeypatch,
) -> None:
    message = Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat.model_construct(id=91, type="private"),
    )
    callback = CallbackQuery.model_construct(
        id="callback",
        from_user=TelegramUser.model_construct(
            id=91, is_bot=False, first_name="target"
        ),
        chat_instance="private",
        message=message,
    )
    answer = AsyncMock()
    selection = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    monkeypatch.setattr(battle, "_show_teacher_selection", selection)
    attack = SimpleNamespace(target_id=7, attacker_id=8, status=AttackStatus.RESOLVED)
    defender = SimpleNamespace(telegram_user_id=91)
    attacker = SimpleNamespace(id=8, is_active=True)

    async def get(_model, identity):
        return {42: attack, 7: defender, 8: attacker}.get(identity)

    session = SimpleNamespace(get=AsyncMock(side_effect=get))
    state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock())
    data = RevengeCallback(action="attack", attack_id=42)
    await battle.revenge_callback_handler(callback, data, session, state)
    state.update_data.assert_awaited_once_with(
        mode="id", target_id=8, selected_teacher_ids=[]
    )
    selection.assert_awaited_once()

    stranger_callback = CallbackQuery.model_construct(
        id="stranger",
        from_user=TelegramUser.model_construct(
            id=92, is_bot=False, first_name="stranger"
        ),
        chat_instance="private",
        message=message,
    )
    state.update_data.reset_mock()
    await battle.revenge_callback_handler(stranger_callback, data, session, state)
    state.update_data.assert_not_awaited()
    assert answer.await_args.kwargs["show_alert"] is True
