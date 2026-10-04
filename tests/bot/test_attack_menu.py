from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from app.bot.callbacks import AttackMenuCallback
from app.bot.custom_emojis import _decorate_markup
from app.bot.handlers import battle
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.services.attack_service import AttackTargetPreview


def teacher(teacher_id: int, name: str = "افلاطون") -> SimpleNamespace:
    return SimpleNamespace(
        id=teacher_id,
        level=3,
        current_hp=80,
        teacher=SimpleNamespace(name=name),
    )


def test_main_menu_attack_button_has_custom_sword_icon() -> None:
    attack_button = next(
        button
        for row in main_menu_keyboard().keyboard
        for button in row
        if button.text == "حمله"
    )

    assert attack_button.icon_custom_emoji_id == "5823192436024813346"


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
    assert labels == ["حمله رندوم", "🎯 حمله با آیدی"]
    assert (
        type_keyboard.inline_keyboard[0][0].icon_custom_emoji_id
        == "5825935099060822018"
    )


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

    resolve.assert_awaited_once_with(ANY, attacker_telegram_id=42, identifier="@target")
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

    assert keyboard.inline_keyboard[0][0].text == "افلاطون (سطح 3)"
    assert keyboard.inline_keyboard[1][0].text == "فراهانی (سطح 3)"
    assert keyboard.inline_keyboard[2][0].text == "حسابی (سطح 3)"

    _decorate_markup({"reply_markup": keyboard})
    teacher_buttons = [row[0] for row in keyboard.inline_keyboard[:-1]]
    assert teacher_buttons[0].icon_custom_emoji_id == "5825709849500985213"
    assert teacher_buttons[1].icon_custom_emoji_id is None
    assert teacher_buttons[2].icon_custom_emoji_id == "5825709849500985213"
    assert keyboard.inline_keyboard[-1][0].style == "success"
    assert keyboard.inline_keyboard[-1][0].text == "تأیید حمله"
    assert keyboard.inline_keyboard[-1][1].style == "danger"
    assert keyboard.inline_keyboard[-1][1].text == "لغو حمله"


@pytest.mark.asyncio
async def test_reply_attack_in_group_opens_teacher_selection(monkeypatch) -> None:
    target_preview = AsyncMock(return_value=SimpleNamespace(id=77))
    show_selection = AsyncMock()
    monkeypatch.setattr(battle.attack_service, "target_preview", target_preview)
    monkeypatch.setattr(battle, "_show_teacher_selection", show_selection)
    state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock())
    message = SimpleNamespace(
        text="حمله",
        chat=SimpleNamespace(type="supergroup"),
        message_id=123,
        from_user=SimpleNamespace(id=42),
        reply_to_message=SimpleNamespace(
            from_user=SimpleNamespace(id=55, is_bot=False)
        ),
    )
    session = AsyncMock()

    await battle.attack_message(message, session, state)

    target_preview.assert_awaited_once_with(
        session, attacker_telegram_id=42, identifier="55"
    )
    state.update_data.assert_awaited_once_with(
        mode="id", target_id=77, selected_teacher_ids=[], group_attacker_id=42
    )
    show_selection.assert_awaited_once_with(
        message, session, state, mode="id", reply_to_message_id=123
    )


@pytest.mark.asyncio
async def test_reply_attack_on_self_shows_requested_message() -> None:
    message = SimpleNamespace(
        text="حمله",
        chat=SimpleNamespace(type="supergroup"),
        from_user=SimpleNamespace(id=42),
        reply_to_message=SimpleNamespace(
            from_user=SimpleNamespace(id=42, is_bot=False)
        ),
        answer=AsyncMock(),
    )

    await battle.attack_message(message, AsyncMock(), AsyncMock())

    assert "نمیتونی به خودت حمله کنی زرنگ" in message.answer.await_args.args[0]
    assert "5920515596088250243" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_other_group_member_cannot_cancel_teacher_selection() -> None:
    message = MagicMock(spec=Message)
    message.edit_text = AsyncMock()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=24), message=message, answer=AsyncMock()
    )
    state = SimpleNamespace(get_data=AsyncMock(), clear=AsyncMock())

    await battle.attack_menu_callback_handler(
        callback,
        AttackMenuCallback(action="cancel", mode="id", attacker_id=42),
        AsyncMock(),
        state,
    )

    assert callback.answer.await_args.kwargs["show_alert"] is True
    state.get_data.assert_not_awaited()
    state.clear.assert_not_awaited()
    message.edit_text.assert_not_awaited()


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

    await battle.attack_menu_callback_handler(callback, data, AsyncMock(), state)

    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "حداکثر 4" in callback.answer.await_args.args[0]
    state.update_data.assert_not_awaited()
    message.edit_reply_markup.assert_not_awaited()
