from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import tic_tac_toe
from app.bot.handlers.tic_tac_toe import (
    amount_game,
    cancel_callback,
    computer_game,
    currency_game,
    friendly_game,
    game_private,
    human_game,
    invitation_keyboard,
    invitation_text,
    result_text,
    select_game,
    sent_invitation_keyboard,
    target_game,
    wager_game,
)
from app.models.tic_tac_toe import TicTacToeGame


@pytest.mark.asyncio
async def test_game_menu_has_both_tic_tac_toe_variants() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await game_private(message, state)

    state.clear.assert_awaited_once_with()
    call = message.answer.await_args
    assert call.args[0] == "یکی از بازی هارو انتخاب کن 🎮"
    assert len(call.kwargs["entities"]) == 1
    assert call.kwargs["entities"][0].custom_emoji_id == "4972415571384599106"
    rows = call.kwargs["reply_markup"].inline_keyboard
    assert len(rows) == 2 and all(len(row) == 1 for row in rows)
    assert rows[0][0].text == "دوز"
    assert rows[0][0].icon_custom_emoji_id == "5222158908805632010"
    assert rows[1][0].text == "دوز پیشرفته"
    assert rows[1][0].callback_data == "ttt:select:advanced"
    assert rows[1][0].icon_custom_emoji_id == rows[0][0].icon_custom_emoji_id


@pytest.mark.asyncio
async def test_advanced_selection_keeps_variant_through_human_flow(monkeypatch) -> None:
    callback = _callback("ttt:select:advanced")
    await select_game(callback)
    buttons = [
        row[0]
        for row in callback.message.edit_text.await_args.kwargs[
            "reply_markup"
        ].inline_keyboard
    ]
    assert [button.callback_data for button in buttons] == [
        "ttt:computer:advanced",
        "ttt:human:advanced",
    ]

    callback.data = "ttt:human:advanced"
    await human_game(callback)
    buttons = [
        row[0]
        for row in callback.message.answer.await_args.kwargs[
            "reply_markup"
        ].inline_keyboard
    ]
    assert [button.callback_data for button in buttons] == [
        "ttt:friendly:advanced",
        "ttt:wager:advanced",
    ]

    monkeypatch.setattr(tic_tac_toe.settings, "TELEGRAM_WIDGET_BETA_ENABLED", True)
    callback.data = "ttt:friendly:advanced"
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    await friendly_game(callback, state)
    state.update_data.assert_awaited_once_with(
        mode="friendly", currency=None, amount=0, variant="advanced"
    )

    callback.data = "ttt:wager:advanced"
    await wager_game(callback)
    buttons = [
        row[0]
        for row in callback.message.edit_text.await_args.kwargs[
            "reply_markup"
        ].inline_keyboard
    ]
    assert [button.callback_data for button in buttons] == [
        "ttt:currency:coin:advanced",
        "ttt:currency:diamond:advanced",
    ]
    callback.data = "ttt:currency:coin:advanced"
    state.update_data.reset_mock()
    await currency_game(callback, state)
    state.update_data.assert_awaited_once_with(
        mode="wager", currency="coin", variant="advanced"
    )


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


def test_sent_invitation_has_cancel_button() -> None:
    button = sent_invitation_keyboard(17).inline_keyboard[0][0]
    assert (button.text, button.callback_data, button.style) == (
        "لغو درخواست",
        "ttt:cancel:17",
        "danger",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["classic", "advanced"])
async def test_sending_either_variant_shows_cancel_button(monkeypatch, variant) -> None:
    game = TicTacToeGame(
        id=17,
        variant=variant,
        mode="friendly",
        stake_amount=0,
        board="." * (100 if variant == "advanced" else 9),
    )
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=43))
    )
    message = SimpleNamespace(
        bot=bot,
        from_user=SimpleNamespace(id=100),
        text="200",
        answer=AsyncMock(return_value=SimpleNamespace(message_id=42)),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"mode": "friendly", "variant": variant}),
        clear=AsyncMock(),
    )
    session = SimpleNamespace(
        scalar=AsyncMock(
            return_value=SimpleNamespace(id=20, telegram_user_id=200, is_active=True)
        ),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(
        tic_tac_toe.users,
        "get_or_create_from_telegram",
        AsyncMock(return_value=SimpleNamespace(id=10, first_name="Atila")),
    )
    monkeypatch.setattr(tic_tac_toe, "create_game", AsyncMock(return_value=game))

    await target_game(message, state, session)

    pending = message.answer.await_args
    assert pending.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        "ttt:cancel:17"
    )
    assert game.challenger_message_id == 42
    assert game.opponent_message_id == 43


@pytest.mark.asyncio
async def test_challenger_cancellation_deletes_opponents_invitation(
    monkeypatch,
) -> None:
    game = TicTacToeGame(
        id=17,
        challenger_id=10,
        opponent_id=20,
        status="cancelled",
        challenger_message_id=42,
        opponent_message_id=43,
    )
    callback = _callback("ttt:cancel:17")
    callback.from_user = SimpleNamespace(id=100)
    callback.bot = SimpleNamespace(delete_message=AsyncMock(return_value=True))
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        tic_tac_toe.users,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=10)),
    )
    monkeypatch.setattr(tic_tac_toe, "cancel_invite", AsyncMock(return_value=game))
    monkeypatch.setattr(tic_tac_toe, "_accounts", AsyncMock(return_value=(100, 200)))
    monkeypatch.setattr(tic_tac_toe, "edit_flow_message", AsyncMock())

    await cancel_callback(callback, session)

    tic_tac_toe.cancel_invite.assert_awaited_once_with(
        session, 17, 10, by_challenger=True
    )
    session.commit.assert_awaited_once()
    callback.bot.delete_message.assert_awaited_once_with(200, 43)
    tic_tac_toe.edit_flow_message.assert_awaited_once_with(
        callback.bot, 100, 42, "درخواست بازی را لغو کردی."
    )
    callback.answer.assert_awaited_once_with("درخواست لغو شد.", show_alert=False)


@pytest.mark.asyncio
async def test_cancelled_invitation_removes_buttons_when_delete_fails(
    monkeypatch,
) -> None:
    game = TicTacToeGame(
        id=17,
        challenger_id=10,
        opponent_id=20,
        status="cancelled",
        challenger_message_id=42,
        opponent_message_id=43,
    )
    callback = _callback("ttt:cancel:17")
    callback.from_user = SimpleNamespace(id=100)
    callback.bot = SimpleNamespace(delete_message=AsyncMock(return_value=False))
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        tic_tac_toe.users,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=10)),
    )
    monkeypatch.setattr(tic_tac_toe, "cancel_invite", AsyncMock(return_value=game))
    monkeypatch.setattr(tic_tac_toe, "_accounts", AsyncMock(return_value=(100, 200)))
    monkeypatch.setattr(tic_tac_toe, "edit_flow_message", AsyncMock())

    await cancel_callback(callback, session)

    assert tic_tac_toe.edit_flow_message.await_args_list[-1].args == (
        callback.bot,
        200,
        43,
        "درخواست بازی لغو شد.",
    )
    callback.answer.assert_awaited_once_with(
        "درخواست لغو شد، ولی حذف پیام حریف انجام نشد.", show_alert=True
    )


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
