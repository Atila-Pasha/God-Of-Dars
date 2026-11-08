"""Five-in-a-row rules and embedded widget contract."""

import json
import zlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.advanced_tic_tac_toe_widget import HTML
from app.bot.handlers import tic_tac_toe
from app.bot.tic_tac_toe_widget import state_json
from app.models.tic_tac_toe import TicTacToeGame
from app.services.tic_tac_toe_service import advanced_computer_move, outcome


def board_with(cells: list[int], mark: str = "X", size: int = 10) -> str:
    board = ["."] * (size * size)
    for cell in cells:
        board[cell] = mark
    return "".join(board)


@pytest.mark.parametrize(
    "cells",
    [
        [0, 1, 2, 3, 4],
        [0, 10, 20, 30, 40],
        [0, 11, 22, 33, 44],
        [9, 18, 27, 36, 45],
        [90, 91, 92, 93, 94],
    ],
)
def test_five_in_a_row_wins_in_every_direction(cells: list[int]) -> None:
    assert outcome(board_with(cells)) == "X"


def test_rows_do_not_wrap_and_four_is_not_a_win() -> None:
    assert outcome(board_with([7, 8, 9, 10, 11])) is None
    assert outcome(board_with([0, 1, 2, 3])) is None
    assert outcome(board_with([0, 15, 30, 45, 60], size=15)) == "X"


def test_computer_takes_win_and_blocks_human_win() -> None:
    assert advanced_computer_move(board_with([54, 55, 56, 57], "O")) in {53, 58}
    assert advanced_computer_move(board_with([54, 55, 56, 57], "X")) in {53, 58}


def test_widget_fits_beta_limits_and_state_is_small() -> None:
    assert len(HTML.encode()) <= 32768
    assert len(zlib.compress(HTML.encode(), 9)) <= 4096
    game = TicTacToeGame(
        id=1,
        challenger_id=10,
        opponent_id=20,
        variant="advanced",
        board="." * 100,
        mode="friendly",
        stake_amount=0,
        status="active",
        turn_id=10,
    )
    data = state_json(game, 100, 200)
    assert len(data.encode()) <= 1024
    assert json.loads(data)["challenger"] == 100
    assert "TelegramWidget.request" in HTML
    assert "TelegramWidget.ready()" in HTML
    assert "setResizeAnchor('top')" in HTML
    assert "chatDataChanged" in HTML
    assert "innerHTML=''" not in HTML
    assert ".row{display:flex;width:100%;height:28px}" in HTML
    assert ".board{width:282px;height:282px" in HTML
    assert "grid-template-rows" not in HTML
    assert "aspect-ratio" not in HTML
    assert '<div class="toolbar"' not in HTML
    assert "opacity:.75" not in HTML
    assert "box-shadow" not in HTML


@pytest.mark.asyncio
async def test_advanced_match_never_sends_inline_keyboard_on_widget_failure(
    monkeypatch,
) -> None:
    game = TicTacToeGame(
        id=2,
        challenger_id=10,
        opponent_id=None,
        variant="advanced",
        board="." * 100,
        mode="computer",
        stake_amount=0,
        status="active",
        turn_id=10,
    )
    monkeypatch.setattr(tic_tac_toe, "_accounts", AsyncMock(return_value=(100, None)))
    monkeypatch.setattr(tic_tac_toe, "widget_api", AsyncMock(return_value=None))
    bot = SimpleNamespace(send_message=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock())
    assert await tic_tac_toe.publish_board(bot, session, game) is False
    tic_tac_toe.widget_api.assert_awaited_once()
    assert "chat_data" in tic_tac_toe.widget_api.await_args.args[2]
    bot.send_message.assert_not_awaited()
