from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from app.bot.callbacks import AttackMenuCallback
from app.bot.handlers import battle
from app.services.attack_service import AttackTargetPreview


def teacher(teacher_id: int, name: str = "افلاطون") -> SimpleNamespace:
    return SimpleNamespace(
        id=teacher_id,
        current_hp=80,
        teacher=SimpleNamespace(name=name),
    )


@pytest.mark.asyncio
async def test_attack_button_replaces_main_menu_with_back_and_attack_types() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await battle.attack_menu_handler(message, state)

    state.clear.assert_awaited_once()
    assert message.answer.await_count == 2
    back_keyboard = message.answer.await_args_list[0].kwargs["reply_markup"]
    assert back_keyboard.keyboard[0][0].text == "بازگشت به منو اصلی"
    type_keyboard = message.answer.await_args_list[1].kwargs["reply_markup"]
    labels = [button.text for button in type_keyboard.inline_keyboard[0]]
    assert labels == ["🎲 حمله رندوم", "🎯 حمله با آیدی"]


@pytest.mark.asyncio
async def test_id_attack_accepts_username_and_shows_target_preview(
    monkeypatch,
) -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        text="@target",
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock())
    preview = AttackTargetPreview(
        id=7,
        telegram_user_id=77,
        first_name="نگار",
        username="target",
    )
    resolve = AsyncMock(return_value=preview)
    monkeypatch.setattr(battle.attack_service, "target_preview", resolve)

    await battle.attack_target_handler(message, AsyncMock(), state)

    resolve.assert_awaited_once_with(
        ANY, attacker_telegram_id=42, identifier="@target"
    )
    state.update_data.assert_awaited_once_with(
        mode="id", target_id=7, selected_teacher_ids=[]
    )
    assert "نگار" in message.answer.await_args.args[0]
    assert "@target" in message.answer.await_args.args[0]
    button = message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert "انتخاب دبیر" in button.text


def test_teacher_selection_keyboard_marks_multiple_teachers() -> None:
    keyboard = battle._teacher_selection_keyboard(
        [teacher(1), teacher(2, "فراهانی"), teacher(3, "حسابی")],
        mode="random",
        selected_ids=[1, 3],
    )

    assert keyboard.inline_keyboard[0][0].text.startswith("✅")
    assert keyboard.inline_keyboard[1][0].text.startswith("⬜️")
    assert keyboard.inline_keyboard[2][0].text.startswith("✅")
    assert "2/4" in keyboard.inline_keyboard[-1][0].text


@pytest.mark.asyncio
async def test_fifth_teacher_cannot_be_selected(monkeypatch) -> None:
    message = MagicMock(spec=Message)
    message.edit_reply_markup = AsyncMock()
    message.answer = AsyncMock()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "mode": "random",
                "selected_teacher_ids": [1, 2, 3, 4],
            }
        ),
        update_data=AsyncMock(),
    )
    monkeypatch.setattr(
        battle.attack_service,
        "available_attack_teachers",
        AsyncMock(
            return_value=[
                teacher(1),
                teacher(2),
                teacher(3),
                teacher(4),
                teacher(5),
            ]
        ),
    )
    data = AttackMenuCallback(action="toggle", mode="random", teacher_id=5)

    await battle.attack_menu_callback_handler(
        callback, data, AsyncMock(), state
    )

    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "حداکثر 4" in callback.answer.await_args.args[0]
    state.update_data.assert_not_awaited()
    message.edit_reply_markup.assert_not_awaited()
