from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from app.bot.callbacks import RandomAttackCallback
from app.bot.handlers import battle
from app.services.attack_service import AttackPreview, RandomAttackPreview
from app.services.school_errors import RandomAttackSelectionExpired


def random_preview(*, version: int = 1) -> RandomAttackPreview:
    return RandomAttackPreview(
        preview=AttackPreview(
            attacker_id=42,
            target_id=7,
            teacher_id=9,
            attacker_name="آرش",
            target_name="نگار",
            teacher_name="افلاطون",
            ability_text=None,
            teacher_damage=50,
            defense_power=20,
            estimated_castle_damage=30,
            estimated_teacher_injury=5,
            loot_coin=25,
            loot_diamond=1,
            loot_banana=0,
            teacher_ids="9",
        ),
        version=version,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        reroll_count=0,
        reroll_coin_cost=25,
    )


def test_attack_preview_shows_every_selected_teacher_emoji() -> None:
    preview = replace(
        random_preview().preview,
        teacher_emojis=("🧠", "🔬", "123456789"),
    )

    text, entities = battle._preview_content(preview)

    assert text.startswith("🧠 🔬 👨‍🏫 پیش‌نمایش حمله")
    assert len(entities) == 1
    assert entities[0].offset == len("🧠 🔬 ".encode("utf-16-le")) // 2
    assert entities[0].custom_emoji_id == "123456789"


def message() -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        text="حمله رندوم افلاطون",
        chat=SimpleNamespace(type="private"),
        message_id=123,
        answer=AsyncMock(),
    )


def callback(
    *, action: str, version: int = 1
) -> tuple[SimpleNamespace, RandomAttackCallback]:
    target = SimpleNamespace(
        delete=AsyncMock(),
        answer=AsyncMock(),
        answer_sticker=AsyncMock(),
        edit_text=AsyncMock(),
    )
    return (
        SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=target,
            answer=AsyncMock(),
        ),
        RandomAttackCallback(
            action=action,
            attacker_id=42,
            version=version,
            source_message_id=123,
        ),
    )


@pytest.mark.asyncio
async def test_random_attack_command_uses_durable_preview_and_reroll_keyboard(
    monkeypatch,
) -> None:
    target = message()
    preview = random_preview()
    prepare = AsyncMock(return_value=preview)
    monkeypatch.setattr(battle.attack_service, "prepare_random_preview", prepare)

    await battle.attack_message(target, AsyncMock())

    prepare.assert_awaited_once_with(
        ANY,
        attacker_telegram_id=42,
        teacher_name="افلاطون",
    )
    text = target.answer.await_args.args[0]
    keyboard = target.answer.await_args.kwargs["reply_markup"]
    assert "25 سکه" in text
    assert "حریف دیگر" in keyboard.inline_keyboard[1][0].text
    assert len(keyboard.inline_keyboard[1][0].callback_data) <= 64


@pytest.mark.asyncio
async def test_random_attack_cancel_only_closes_preview(monkeypatch) -> None:
    event, data = callback(action="cancel")
    reroll = AsyncMock()
    launch = AsyncMock()
    monkeypatch.setattr(battle.attack_service, "reroll_random_preview", reroll)
    monkeypatch.setattr(battle.attack_service, "launch_random_attack", launch)

    await battle.random_attack_confirmation(event, data, AsyncMock())

    event.message.delete.assert_awaited_once()
    reroll.assert_not_awaited()
    launch.assert_not_awaited()
    assert "ثابت" in event.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_other_group_member_cannot_use_random_attack_buttons(monkeypatch) -> None:
    event, data = callback(action="reroll")
    event.from_user.id = 99
    reroll = AsyncMock()
    monkeypatch.setattr(battle.attack_service, "reroll_random_preview", reroll)

    await battle.random_attack_confirmation(event, data, AsyncMock())

    reroll.assert_not_awaited()
    assert event.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_random_attack_reroll_commits_once_and_replaces_keyboard(
    monkeypatch,
) -> None:
    event, data = callback(action="reroll")
    session = SimpleNamespace(commit=AsyncMock())
    reroll = AsyncMock(return_value=random_preview(version=2))
    monkeypatch.setattr(battle.attack_service, "reroll_random_preview", reroll)

    await battle.random_attack_confirmation(event, data, session)

    reroll.assert_awaited_once_with(session, attacker_telegram_id=42, version=1)
    session.commit.assert_awaited_once()
    assert (
        "حریف دیگر"
        in event.message.edit_text.await_args.kwargs["reply_markup"]
        .inline_keyboard[1][0]
        .text
    )


@pytest.mark.asyncio
async def test_stale_random_reroll_is_not_charged_again(monkeypatch) -> None:
    event, data = callback(action="reroll", version=1)
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        battle.attack_service,
        "reroll_random_preview",
        AsyncMock(side_effect=RandomAttackSelectionExpired),
    )

    await battle.random_attack_confirmation(event, data, session)

    session.commit.assert_not_awaited()
    assert "معتبر نیست" in event.message.answer.await_args.args[0]
