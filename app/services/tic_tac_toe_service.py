"""Authoritative tic-tac-toe rules and atomic wager settlement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import cache

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.resource import Resource
from app.models.tic_tac_toe import TicTacToeGame
from app.models.transaction import Transaction
from app.models.user import User

TURN_SECONDS = 60
INVITE_MINUTES = 5
LIVE = ("invited", "active")
LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class GameError(ValueError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def outcome(board: str) -> str | None:
    for a, b, c in LINES:
        if board[a] != "." and board[a] == board[b] == board[c]:
            return board[a]
    return "draw" if "." not in board else None


def computer_move(board: str) -> int:
    """Perfect play, with center/corner preference for equal scores."""

    @cache
    def score(position: str, cpu_turn: bool, depth: int) -> int:
        result = outcome(position)
        if result == "O":
            return 10 - depth
        if result == "X":
            return depth - 10
        if result == "draw":
            return 0
        values = [
            score(
                position[:i] + ("O" if cpu_turn else "X") + position[i + 1 :],
                not cpu_turn,
                depth + 1,
            )
            for i, cell in enumerate(position)
            if cell == "."
        ]
        return max(values) if cpu_turn else min(values)

    choices = [i for i in (4, 0, 2, 6, 8, 1, 3, 5, 7) if board[i] == "."]
    return max(choices, key=lambda i: score(board[:i] + "O" + board[i + 1 :], False, 0))


async def _active_for(
    session: AsyncSession, user_id: int, *, except_id: int | None = None
) -> bool:
    stmt = select(TicTacToeGame.id).where(
        TicTacToeGame.status.in_(LIVE),
        or_(
            TicTacToeGame.challenger_id == user_id, TicTacToeGame.opponent_id == user_id
        ),
    )
    if except_id is not None:
        stmt = stmt.where(TicTacToeGame.id != except_id)
    return (await session.scalar(stmt.limit(1))) is not None


async def _lock_users(session: AsyncSession, ids: list[int]) -> None:
    for user_id in sorted(set(ids)):
        await session.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )


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
    session: AsyncSession, row: Resource, game: TicTacToeGame, delta: int, reason: str
) -> None:
    if game.stake_type not in {"coin", "diamond"}:
        raise GameError("این شرط معتبر نیست.")
    kind = ResourceType.COIN if game.stake_type == "coin" else ResourceType.DIAMOND
    field = game.stake_type
    before = getattr(row, field)
    if before + delta < 0:
        raise GameError("موجودی کافی نیست.")
    setattr(row, field, before + delta)
    session.add(
        Transaction(
            user_id=row.user_id,
            resource_type=kind,
            amount=delta,
            balance_before=before,
            balance_after=before + delta,
            reason=reason,
            reference_type="tic_tac_toe",
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
) -> TicTacToeGame:
    if mode not in {"computer", "friendly", "wager"} or (mode == "computer") != (
        opponent_id is None
    ):
        raise GameError("این نوع بازی معتبر نیست.")
    if opponent_id == challenger_id:
        raise GameError("نمی‌تونی با خودت بازی کنی.")
    if mode == "wager" and (stake_type not in {"coin", "diamond"} or amount < 1):
        raise GameError("این شرط معتبر نیست.")
    if mode != "wager" and (stake_type is not None or amount != 0):
        raise GameError("این شرط معتبر نیست.")
    ids = [challenger_id] + ([opponent_id] if opponent_id is not None else [])
    await _lock_users(session, ids)
    for user_id in ids:
        if await _active_for(session, user_id):
            raise GameError("یکی از شما الان توی یه بازیه یا دعوت فعال داره.")
    if mode == "wager":
        if stake_type is None:
            raise GameError("این شرط معتبر نیست.")
        rows = await _resources(session, ids)
        for user_id in ids:
            if user_id not in rows or getattr(rows[user_id], stake_type) < amount:
                who = "حریف" if user_id == opponent_id else "تو"
                raise GameError(
                    f"بازی لغو شد. {who} به اندازهٔ {amount:,} موجودی نداره."
                )
    game = TicTacToeGame(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        mode=mode,
        stake_type=stake_type,
        stake_amount=amount,
        status="active" if mode == "computer" else "invited",
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
) -> TicTacToeGame:
    candidate = await session.get(TicTacToeGame, game_id)
    if candidate is None or candidate.opponent_id != opponent_id:
        raise GameError("این دعوت برای تو نیست.")
    await _lock_users(session, [candidate.challenger_id, opponent_id])
    game = await session.scalar(
        select(TicTacToeGame)
        .where(TicTacToeGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        game is None
        or game.status != "invited"
        or game.deadline_at is None
        or game.deadline_at <= now()
    ):
        raise GameError("این دعوت دیگه فعال نیست.")
    if await _active_for(
        session, game.challenger_id, except_id=game.id
    ) or await _active_for(session, opponent_id, except_id=game.id):
        raise GameError("یکی از شما وارد یه بازی دیگه شده.")
    if game.mode == "wager":
        if game.stake_type not in {"coin", "diamond"}:
            raise GameError("این شرط معتبر نیست.")
        rows = await _resources(session, [game.challenger_id, opponent_id])
        for user_id in (game.challenger_id, opponent_id):
            if (
                user_id not in rows
                or getattr(rows[user_id], game.stake_type) < game.stake_amount
            ):
                game.status = "cancelled"
                game.deadline_at = None
                return game
        for user_id in (game.challenger_id, opponent_id):
            _entry(session, rows[user_id], game, -game.stake_amount, "ttt_escrow")
        game.escrowed = True
    game.status = "active"
    game.turn_id = game.challenger_id
    game.deadline_at = now() + timedelta(seconds=TURN_SECONDS)
    return game


async def _finish(
    session: AsyncSession,
    game: TicTacToeGame,
    winner_id: int | None,
    status: str = "finished",
) -> None:
    game.status = status
    game.winner_id = winner_id
    game.turn_id = None
    game.deadline_at = None
    if game.escrowed:
        if game.opponent_id is None:
            raise GameError("حریف بازی پیدا نشد.")
        participant_ids = (game.challenger_id, game.opponent_id)
        rows = await _resources(session, list(participant_ids))
        if winner_id is None:
            for user_id in participant_ids:
                _entry(session, rows[user_id], game, game.stake_amount, "ttt_refund")
        else:
            _entry(session, rows[winner_id], game, game.stake_amount * 2, "ttt_win")
        game.escrowed = False


async def cancel_invite(
    session: AsyncSession, game_id: int, actor_id: int
) -> TicTacToeGame:
    game = await session.scalar(
        select(TicTacToeGame).where(TicTacToeGame.id == game_id).with_for_update()
    )
    if (
        game is None
        or actor_id not in (game.challenger_id, game.opponent_id)
        or game.status != "invited"
    ):
        raise GameError("این دعوت دیگه فعال نیست.")
    await _finish(session, game, None, "cancelled")
    return game


async def move(
    session: AsyncSession, game_id: int, actor_id: int, cell: int
) -> TicTacToeGame:
    game = await session.scalar(
        select(TicTacToeGame)
        .where(TicTacToeGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None or actor_id not in (game.challenger_id, game.opponent_id):
        raise GameError("بازی رو پیدا نکردم.")
    if game.status != "active":
        raise GameError("بازی تموم شده.")
    if game.deadline_at is None:
        raise GameError("بازی تموم شده.")
    if game.deadline_at <= now():
        winner = (
            (game.opponent_id or -1)
            if game.turn_id == game.challenger_id
            else game.challenger_id
        )
        await _finish(session, game, winner)
        return game
    if game.turn_id != actor_id:
        raise GameError("الان نوبت تو نیست.")
    if cell not in range(9) or game.board[cell] != ".":
        raise GameError("این خونه پره یا معتبر نیست.")
    mark = "X" if actor_id == game.challenger_id else "O"
    game.board = game.board[:cell] + mark + game.board[cell + 1 :]
    result = outcome(game.board)
    if result is not None:
        await _finish(session, game, actor_id if result != "draw" else None)
        return game
    if game.mode == "computer":
        cpu = computer_move(game.board)
        game.board = game.board[:cpu] + "O" + game.board[cpu + 1 :]
        result = outcome(game.board)
        if result is not None:
            await _finish(session, game, -1 if result == "O" else None)
            return game
        game.turn_id = game.challenger_id
    else:
        game.turn_id = (
            game.opponent_id if actor_id == game.challenger_id else game.challenger_id
        )
    game.deadline_at = now() + timedelta(seconds=TURN_SECONDS)
    return game


async def expire_game(session: AsyncSession, game_id: int) -> TicTacToeGame | None:
    game = await session.scalar(
        select(TicTacToeGame)
        .where(TicTacToeGame.id == game_id)
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
        winner = (
            (game.opponent_id or -1)
            if game.turn_id == game.challenger_id
            else game.challenger_id
        )
        await _finish(session, game, winner)
    return game
