"""Server-authoritative chess rules, invitations, clocks and wager settlement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import chess
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.chess_game import ChessGame
from app.models.resource import Resource
from app.models.tic_tac_toe import TicTacToeGame
from app.models.transaction import Transaction
from app.models.user import User

TURN_SECONDS = 60
INVITE_MINUTES = 5
LIVE = ("invited", "active")
PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 335,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


class ChessError(ValueError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def board_for(game: ChessGame) -> chess.Board:
    """Replay moves so castling, en passant and repetition remain authoritative."""
    board = chess.Board()
    for uci in game.moves.split():
        board.push_uci(uci)
    return board


def _evaluate(board: chess.Board) -> int:
    result = board.outcome(claim_draw=True)
    if result is not None:
        return (
            100_000
            if result.winner is chess.BLACK
            else -100_000
            if result.winner is chess.WHITE
            else 0
        )
    total = 0
    for square, piece in board.piece_map().items():
        rank = chess.square_rank(square)
        file = chess.square_file(square)
        center = 6 - abs(file - 3.5) - abs(rank - 3.5)
        advance = (6 - rank) if piece.color is chess.BLACK else (rank - 1)
        value = PIECE_VALUE[piece.piece_type] + int(center * 3)
        if piece.piece_type == chess.PAWN:
            value += advance * 5
        total += value if piece.color is chess.BLACK else -value
    return total


def computer_move(board: chess.Board) -> chess.Move:
    """Choose a legal black move by evaluating the best white reply."""
    if board.turn is not chess.BLACK:
        raise ChessError("نوبت ربات نیست.")
    best_move = None
    best_score = -(10**9)
    for candidate in board.legal_moves:
        board.push(candidate)
        if board.is_game_over(claim_draw=True):
            score = _evaluate(board)
        else:
            score = 10**9
            for reply in board.legal_moves:
                board.push(reply)
                score = min(score, _evaluate(board))
                board.pop()
        board.pop()
        if score > best_score:
            best_move, best_score = candidate, score
    if best_move is None:
        raise ChessError("حرکت قانونی برای ربات وجود ندارد.")
    return best_move


async def _lock_users(session: AsyncSession, ids: list[int]) -> None:
    for user_id in sorted(set(ids)):
        await session.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )


async def _active_for(
    session: AsyncSession, user_id: int, *, except_id: int | None = None
) -> bool:
    own = select(ChessGame.id).where(
        ChessGame.status.in_(LIVE),
        or_(ChessGame.challenger_id == user_id, ChessGame.opponent_id == user_id),
    )
    if except_id is not None:
        own = own.where(ChessGame.id != except_id)
    if await session.scalar(own.limit(1)) is not None:
        return True
    other = select(TicTacToeGame.id).where(
        TicTacToeGame.status.in_(LIVE),
        or_(
            TicTacToeGame.challenger_id == user_id, TicTacToeGame.opponent_id == user_id
        ),
    )
    return await session.scalar(other.limit(1)) is not None


async def _resources(session: AsyncSession, ids: list[int]) -> dict[int, Resource]:
    rows = (
        await session.scalars(
            select(Resource)
            .where(Resource.user_id.in_(ids))
            .order_by(Resource.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    return {row.user_id: row for row in rows}


def _entry(
    session: AsyncSession, row: Resource, game: ChessGame, delta: int, reason: str
) -> None:
    if game.stake_type not in {"coin", "diamond"}:
        raise ChessError("این شرط معتبر نیست.")
    before = getattr(row, game.stake_type)
    if before + delta < 0:
        raise ChessError("موجودی کافی نیست.")
    setattr(row, game.stake_type, before + delta)
    session.add(
        Transaction(
            user_id=row.user_id,
            resource_type=ResourceType.COIN
            if game.stake_type == "coin"
            else ResourceType.DIAMOND,
            amount=delta,
            balance_before=before,
            balance_after=before + delta,
            reason=reason,
            reference_type="chess",
            reference_id=game.id,
        )
    )


async def create_game(
    session: AsyncSession,
    challenger_id: int,
    opponent_id: int | None,
    mode: str,
    stake_type: str | None = None,
    amount: int = 0,
) -> ChessGame:
    if mode not in {"computer", "friendly", "wager"} or (mode == "computer") != (
        opponent_id is None
    ):
        raise ChessError("این نوع بازی معتبر نیست.")
    if opponent_id == challenger_id:
        raise ChessError("نمی‌تونی با خودت بازی کنی.")
    if mode == "wager":
        if stake_type not in {"coin", "diamond"} or amount < 1:
            raise ChessError("این شرط معتبر نیست.")
    elif stake_type is not None or amount != 0:
        raise ChessError("این شرط معتبر نیست.")
    ids = [challenger_id] + ([opponent_id] if opponent_id is not None else [])
    await _lock_users(session, ids)
    for user_id in ids:
        if await _active_for(session, user_id):
            raise ChessError("یکی از شما الان توی یه بازیه یا دعوت فعال داره.")
    if mode == "wager":
        rows = await _resources(session, ids)
        for user_id in ids:
            if user_id not in rows or getattr(rows[user_id], stake_type) < amount:
                who = "حریف" if user_id == opponent_id else "تو"
                raise ChessError(
                    f"بازی لغو شد. {who} به اندازهٔ {amount:,} موجودی نداره."
                )
    game = ChessGame(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        mode=mode,
        stake_type=stake_type,
        stake_amount=amount,
        status="active" if mode == "computer" else "invited",
        moves="",
        turn_id=challenger_id if mode == "computer" else None,
        deadline_at=now()
        + (
            timedelta(seconds=TURN_SECONDS)
            if mode == "computer"
            else timedelta(minutes=INVITE_MINUTES)
        ),
    )
    session.add(game)
    await session.flush()
    return game


async def accept_game(
    session: AsyncSession, game_id: int, opponent_id: int
) -> ChessGame:
    candidate = await session.get(ChessGame, game_id)
    if candidate is None or candidate.opponent_id != opponent_id:
        raise ChessError("این دعوت برای تو نیست.")
    await _lock_users(session, [candidate.challenger_id, opponent_id])
    game = await session.scalar(
        select(ChessGame)
        .where(ChessGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        game is None
        or game.status != "invited"
        or game.deadline_at is None
        or game.deadline_at <= now()
    ):
        raise ChessError("این دعوت دیگه فعال نیست.")
    if await _active_for(
        session, game.challenger_id, except_id=game.id
    ) or await _active_for(session, opponent_id, except_id=game.id):
        raise ChessError("یکی از شما وارد یه بازی دیگه شده.")
    if game.mode == "wager":
        rows = await _resources(session, [game.challenger_id, opponent_id])
        if game.stake_type not in {"coin", "diamond"}:
            raise ChessError("این شرط معتبر نیست.")
        if any(
            user_id not in rows
            or getattr(rows[user_id], game.stake_type) < game.stake_amount
            for user_id in (game.challenger_id, opponent_id)
        ):
            game.status, game.deadline_at = "cancelled", None
            return game
        for user_id in (game.challenger_id, opponent_id):
            _entry(session, rows[user_id], game, -game.stake_amount, "chess_escrow")
        game.escrowed = True
    game.status = "active"
    game.turn_id = game.challenger_id
    game.deadline_at = now() + timedelta(seconds=TURN_SECONDS)
    return game


async def _finish(
    session: AsyncSession,
    game: ChessGame,
    winner_id: int | None,
    status: str = "finished",
) -> None:
    game.status, game.winner_id, game.turn_id, game.deadline_at = (
        status,
        winner_id,
        None,
        None,
    )
    if game.escrowed:
        if game.opponent_id is None:
            raise ChessError("حریف بازی پیدا نشد.")
        ids = (game.challenger_id, game.opponent_id)
        rows = await _resources(session, list(ids))
        if winner_id is None:
            for user_id in ids:
                _entry(session, rows[user_id], game, game.stake_amount, "chess_refund")
        else:
            _entry(session, rows[winner_id], game, game.stake_amount * 2, "chess_win")
        game.escrowed = False


async def cancel_invite(
    session: AsyncSession,
    game_id: int,
    actor_id: int,
    *,
    by_challenger: bool | None = None,
) -> ChessGame:
    game = await session.scalar(
        select(ChessGame)
        .where(ChessGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        game is None
        or actor_id not in (game.challenger_id, game.opponent_id)
        or (by_challenger is True and actor_id != game.challenger_id)
        or (by_challenger is False and actor_id != game.opponent_id)
        or game.status != "invited"
    ):
        raise ChessError("این دعوت دیگه فعال نیست.")
    await _finish(session, game, None, "cancelled")
    return game


async def abort_game(session: AsyncSession, game_id: int) -> ChessGame:
    game = await session.scalar(
        select(ChessGame)
        .where(ChessGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None or game.status != "active":
        raise ChessError("بازی فعال نیست.")
    await _finish(session, game, None, "cancelled")
    return game


def _winner(game: ChessGame, board: chess.Board) -> int | None:
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return None
    return (
        game.challenger_id
        if outcome.winner is chess.WHITE
        else (game.opponent_id or -1)
    )


async def move(
    session: AsyncSession, game_id: int, actor_id: int, uci: str
) -> ChessGame:
    game = await session.scalar(
        select(ChessGame)
        .where(ChessGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None or actor_id not in (game.challenger_id, game.opponent_id):
        raise ChessError("بازی رو پیدا نکردم.")
    if game.status != "active" or game.deadline_at is None:
        raise ChessError("بازی تموم شده.")
    if game.deadline_at <= now():
        await _finish(
            session,
            game,
            (game.opponent_id or -1)
            if game.turn_id == game.challenger_id
            else game.challenger_id,
        )
        return game
    if game.turn_id != actor_id:
        raise ChessError("الان نوبت تو نیست.")
    board = board_for(game)
    try:
        candidate = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise ChessError("حرکت معتبر نیست.") from exc
    if candidate not in board.legal_moves:
        raise ChessError("حرکت قانونی نیست.")
    board.push(candidate)
    game.moves = f"{game.moves} {uci}".strip()
    if board.is_game_over(claim_draw=True):
        await _finish(session, game, _winner(game, board))
        return game
    if game.mode == "computer":
        reply = computer_move(board)
        board.push(reply)
        game.moves += " " + reply.uci()
        if board.is_game_over(claim_draw=True):
            await _finish(session, game, _winner(game, board))
            return game
        game.turn_id = game.challenger_id
    else:
        game.turn_id = (
            game.opponent_id if actor_id == game.challenger_id else game.challenger_id
        )
    game.deadline_at = now() + timedelta(seconds=TURN_SECONDS)
    return game


async def expire_game(session: AsyncSession, game_id: int) -> ChessGame | None:
    game = await session.scalar(
        select(ChessGame)
        .where(ChessGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        game is None
        or game.status not in LIVE
        or game.deadline_at is None
        or game.deadline_at > now()
    ):
        return None
    if game.status == "invited":
        await _finish(session, game, None, "cancelled")
    else:
        await _finish(
            session,
            game,
            (game.opponent_id or -1)
            if game.turn_id == game.challenger_id
            else game.challenger_id,
        )
    return game
