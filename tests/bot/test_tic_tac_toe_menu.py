from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import tic_tac_toe
from app.bot.handlers.tic_tac_toe import (
    amount_game,
    computer_game,
    currency_game,
    friendly_game,
    game_private,
    human_game,
    invitation_keyboard,
    invitation_text,
    result_text,
    select_game,
    wager_game,
)
from app.models.tic_tac_toe import TicTacToeGame


@pytest.mark.asyncio
async def test_game_menu_has_requested_premium_emoji_and_only_tic_tac_toe() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await game_private(message, state)

    state.clear.assert_awaited_once_with()
    call = message.answer.await_args
    assert call.args[0] == "یکی از بازی هارو انتخاب کن 🎮"
    assert len(call.kwargs["entities"]) == 1
    assert call.kwargs["entities"][0].custom_emoji_id == "4972415571384599106"
    rows = call.kwargs["reply_markup"].inline_keyboard
    assert len(rows) == 1 and len(rows[0]) == 1
    assert rows[0][0].text == "دوز"
    assert rows[0][0].icon_custom_emoji_id == "5222158908805632010"


def _callback(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        message=SimpleNamespace(
            message_id=42, edit_text=AsyncMock(), answer=AsyncMock()
        ),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_game_selection_edits_same_message_with_requested_buttons() -> None:
    callback = _callback("ttt:select")
    await select_game(callback)

    call = callback.message.edit_text.await_args
    assert call.args[0] == "میخوای با ربات بازی کنی یا حریف واقعی؟"
    buttons = [row[0] for row in call.kwargs["reply_markup"].inline_keyboard]
    assert [(button.text, button.icon_custom_emoji_id) for button in buttons] == [
        ("ربات", "5803143039060808890"),
        ("حریف واقعی", "5258011929993026890"),
    ]


@pytest.mark.asyncio
async def test_computer_choice_sends_new_start_message(monkeypatch) -> None:
    callback = _callback("ttt:computer")
    callback.from_user = SimpleNamespace(id=7)
    callback.bot = SimpleNamespace()
    state = SimpleNamespace(clear=AsyncMock())
    session = SimpleNamespace()
    monkeypatch.setattr(
        tic_tac_toe.users,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(id=12)),
    )
    monkeypatch.setattr(tic_tac_toe, "create_game", AsyncMock(return_value=object()))
    monkeypatch.setattr(tic_tac_toe, "publish_board", AsyncMock())

    await computer_game(callback, session, state)

    callback.message.answer.assert_awaited_once_with("بازی با ربات شروع شد. نوبت توئه!")
    callback.message.edit_text.assert_not_awaited()
    tic_tac_toe.publish_board.assert_awaited_once()


@pytest.mark.asyncio
async def test_human_options_and_target_prompt_use_new_messages() -> None:
    callback = _callback("ttt:human")
    await human_game(callback)
    call = callback.message.answer.await_args
    assert call.args[0] == "میخوای دوستانه بازی کنی یا شرطی؟"
    buttons = [row[0] for row in call.kwargs["reply_markup"].inline_keyboard]
    assert [(button.text, button.icon_custom_emoji_id) for button in buttons] == [
        ("دوستانه", "5944970130554359187"),
        ("شرطی", "5255934553096202209"),
    ]

    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    await friendly_game(callback, state)
    state.update_data.assert_awaited_once_with(mode="friendly", currency=None, amount=0)
    call = callback.message.answer.await_args
    assert call.kwargs["text"].startswith("آیدی حریف رو بفرست. @username")
    assert call.kwargs["entities"][0].custom_emoji_id == "5845880789744488517"


@pytest.mark.asyncio
async def test_wager_options_and_typed_amount_send_new_messages() -> None:
    callback = _callback("ttt:wager")
    await wager_game(callback)
    buttons = [
        row[0]
        for row in callback.message.edit_text.await_args.kwargs[
            "reply_markup"
        ].inline_keyboard
    ]
    assert [(button.text, button.icon_custom_emoji_id) for button in buttons] == [
        ("طلا", "5825699971076202989"),
        ("الماس", "5235630047959727475"),
    ]

    callback.data = "ttt:currency:coin"
    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )
    await currency_game(callback, state)
    state.update_data.assert_awaited_once_with(mode="wager", currency="coin")
    assert "چقدر طلا" in callback.message.answer.await_args.args[0]

    message = SimpleNamespace(text="۱۲۳", answer=AsyncMock())
    await amount_game(message, state)
    message.answer.assert_awaited_once()
    call = message.answer.await_args
    assert call.kwargs["entities"][0].custom_emoji_id == "5845880789744488517"


def test_invitation_uses_game_details_premium_icons_and_colored_buttons() -> None:
    game = TicTacToeGame(id=17, mode="wager", stake_type="coin", stake_amount=200)
    rendered = invitation_text(game, "AtilA").as_kwargs()
    assert rendered["text"] == (
        "درخواست بازی دوز 🎮\n"
        "اسم حریف: AtilA\n"
        "نوع بازی: شرطی\n"
        "مقدار شرط: 200 طلا 🪙\n"
        "قبول میکنی؟"
    )
    assert [entity.custom_emoji_id for entity in rendered["entities"]] == [
        "4972415571384599106",
        "5825699971076202989",
    ]
    buttons = [row[0] for row in invitation_keyboard(game.id).inline_keyboard]
    assert [(button.style, button.callback_data) for button in buttons] == [
        ("success", "ttt:accept:17"),
        ("danger", "ttt:decline:17"),
    ]

    friendly = TicTacToeGame(mode="friendly", stake_amount=0)
    text = invitation_text(friendly, "AtilA").as_kwargs()["text"]
    assert "نوع بازی: دوستانه" in text
    assert "مقدار شرط:" not in text


def test_game_result_reports_net_wager_change() -> None:
    game = TicTacToeGame(
        mode="wager", stake_type="diamond", stake_amount=5, winner_id=10
    )
    winner = result_text(game, 10).as_kwargs()
    assert winner["text"] == "بردی! 🎉\nتغییر موجودی: +5 الماس"
    assert [entity.type for entity in winner["entities"]] == [
        "bold",
        "custom_emoji",
        "bold",
    ]
    assert winner["entities"][1].custom_emoji_id == "5832496894261071430"
    loser = result_text(game, 20).as_kwargs()
    assert loser["text"] == "باختی! 😢\nتغییر موجودی: −5 الماس"
    assert loser["entities"][1].custom_emoji_id == "5823187398028168504"
    game.winner_id = None
    assert result_text(game, 10).as_kwargs()["text"] == (
        "بازی مساوی شد.\nتغییر موجودی: ۰"
    )
