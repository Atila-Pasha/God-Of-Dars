import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.resource import Resource
from app.models.tic_tac_toe import TicTacToeGame
from app.models.transaction import Transaction
from app.models.user import User
from app.services.tic_tac_toe_service import (
    GameError,
    abort_game,
    accept_game,
    cancel_invite,
    create_game,
    expire_game,
    move,
    now,
)


@pytest.mark.asyncio
async def test_advanced_wager_win_and_widget_failure_refund() -> None:
    first, second = await _player(), await _player()
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(
                session, first, second, "wager", "coin", 10, "advanced"
            )
            assert len(game.board) == 100
            game_id = game.id
            await session.commit()
        async with AsyncSessionLocal() as session:
            game = await accept_game(session, game_id, second)
            board = ["."] * 100
            for cell in (0, 1, 2, 3):
                board[cell] = "X"
            for cell in (10, 12, 14, 16):
                board[cell] = "O"
            game.board = "".join(board)
            game.turn_id = first
            await session.commit()
        async with AsyncSessionLocal() as session:
            game = await move(session, game_id, first, 4)
            await session.commit()
            assert game.status == "finished" and game.winner_id == first
            assert game.last_move == 4
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [110, 90]
            with pytest.raises(GameError):
                await move(session, game_id, second, 5)

        async with AsyncSessionLocal() as session:
            game = await create_game(
                session, first, second, "wager", "coin", 10, "advanced"
            )
            refund_id = game.id
            await session.commit()
        async with AsyncSessionLocal() as session:
            await accept_game(session, refund_id, second)
            await abort_game(session, refund_id)
            await session.commit()
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [110, 90]
    finally:
        await _cleanup((first, second))


@pytest.mark.asyncio
async def test_cancel_invitation_is_challenger_only_and_beats_late_accept() -> None:
    first, second = await _player(), await _player()
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(
                session, first, second, "wager", "coin", 10, "advanced"
            )
            game_id = game.id
            await session.commit()
        async with AsyncSessionLocal() as session:
            with pytest.raises(GameError):
                await cancel_invite(session, game_id, second, by_challenger=True)
            with pytest.raises(GameError):
                await cancel_invite(session, game_id, first, by_challenger=False)
            await cancel_invite(session, game_id, first, by_challenger=True)
            await session.commit()
        async with AsyncSessionLocal() as session:
            with pytest.raises(GameError):
                await accept_game(session, game_id, second)
            game = await session.get(TicTacToeGame, game_id)
            assert game.status == "cancelled"
            assert game.deadline_at is None
            assert not game.escrowed
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [100, 100]
    finally:
        await _cleanup((first, second))


@pytest.mark.asyncio
async def test_accept_and_cancel_race_has_one_winner() -> None:
    first, second = await _player(), await _player()
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(
                session, first, second, "wager", "coin", 10, "advanced"
            )
            game_id = game.id
            await session.commit()

        async def decide(accept: bool) -> bool:
            async with AsyncSessionLocal() as session:
                try:
                    if accept:
                        await accept_game(session, game_id, second)
                    else:
                        await cancel_invite(session, game_id, first, by_challenger=True)
                    await session.commit()
                    return True
                except GameError:
                    await session.rollback()
                    return False

        results = await asyncio.gather(decide(True), decide(False))
        assert results.count(True) == 1
        async with AsyncSessionLocal() as session:
            game = await session.get(TicTacToeGame, game_id)
            assert game.status in {"active", "cancelled"}
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == ([90, 90] if game.status == "active" else [100, 100])
    finally:
        await _cleanup((first, second))


async def _player(coin: int = 100, diamond: int = 5) -> int:
    async with AsyncSessionLocal() as session:
        user = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000), first_name="ttt test"
        )
        user.resources = Resource(coin=coin, diamond=diamond)
        session.add(user)
        await session.commit()
        return user.id


async def _players(count: int, coin: int = 100) -> list[int]:
    async with AsyncSessionLocal() as session:
        players = [
            User(
                telegram_user_id=int(uuid4().int % 2_000_000_000),
                first_name="ttt load test",
                resources=Resource(coin=coin),
            )
            for _ in range(count)
        ]
        session.add_all(players)
        await session.commit()
        return [player.id for player in players]


async def _cleanup(ids: tuple[int, int]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Transaction).where(Transaction.user_id.in_(ids)))
        await session.execute(
            delete(TicTacToeGame).where(TicTacToeGame.challenger_id.in_(ids))
        )
        await session.execute(delete(User).where(User.id.in_(ids)))
        await session.commit()


@pytest.mark.asyncio
async def test_wager_is_reserved_then_paid_once_to_winner() -> None:
    first, second = await _player(), await _player()
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(session, first, second, "wager", "coin", 20)
            game_id = game.id
            await session.commit()
        async with AsyncSessionLocal() as session:
            await accept_game(session, game_id, second)
            await session.commit()
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [80, 80]
            for actor, cell in (
                (first, 0),
                (second, 3),
                (first, 1),
                (second, 4),
                (first, 2),
            ):
                game = await move(session, game_id, actor, cell)
            await session.commit()
            assert game.winner_id == first
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [120, 80]
            with pytest.raises(GameError):
                await move(session, game_id, first, 5)
    finally:
        await _cleanup((first, second))


@pytest.mark.asyncio
async def test_timeout_pays_other_player_and_rejects_late_move() -> None:
    first, second = await _player(), await _player()
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(session, first, second, "wager", "diamond", 2)
            game_id = game.id
            await session.commit()
        async with AsyncSessionLocal() as session:
            game = await accept_game(session, game_id, second)
            game.deadline_at = now() - timedelta(seconds=1)
            await session.commit()
        async with AsyncSessionLocal() as session:
            game = await expire_game(session, game_id)
            await session.commit()
            assert game.winner_id == second
            assert await expire_game(session, game_id) is None
            balances = (
                await session.scalars(
                    select(Resource.diamond)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [3, 7]
    finally:
        await _cleanup((first, second))


@pytest.mark.asyncio
async def test_draw_refunds_both_stakes() -> None:
    first, second = await _player(), await _player()
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(session, first, second, "wager", "coin", 10)
            game_id = game.id
            await session.commit()
            await accept_game(session, game_id, second)
            for actor, cell in (
                (first, 0),
                (second, 1),
                (first, 2),
                (second, 4),
                (first, 3),
                (second, 5),
                (first, 7),
                (second, 6),
                (first, 8),
            ):
                game = await move(session, game_id, actor, cell)
            await session.commit()
            assert game.status == "finished" and game.winner_id is None
            balances = (
                await session.scalars(
                    select(Resource.coin)
                    .where(Resource.user_id.in_((first, second)))
                    .order_by(Resource.user_id)
                )
            ).all()
            assert balances == [100, 100]
    finally:
        await _cleanup((first, second))


@pytest.mark.asyncio
async def test_100_parallel_wagers_settle_without_losing_resources() -> None:
    ids = await _players(200)
    pairs = list(zip(ids[::2], ids[1::2], strict=True))

    async def invite(first: int, second: int) -> int:
        async with AsyncSessionLocal() as session:
            game = await create_game(session, first, second, "wager", "coin", 10)
            await session.commit()
            return game.id

    async def accept(game_id: int, second: int) -> None:
        async with AsyncSessionLocal() as session:
            game = await accept_game(session, game_id, second)
            game.deadline_at = now() - timedelta(seconds=1)
            await session.commit()

    async def settle(game_id: int) -> int | None:
        async with AsyncSessionLocal() as session:
            game = await expire_game(session, game_id)
            await session.commit()
            return game.winner_id if game is not None else None

    try:
        game_ids = await asyncio.gather(
            *(invite(first, second) for first, second in pairs)
        )
        await asyncio.gather(
            *(
                accept(game_id, second)
                for game_id, (_, second) in zip(game_ids, pairs, strict=True)
            )
        )
        winners = await asyncio.gather(*(settle(game_id) for game_id in game_ids))
        assert winners == [second for _, second in pairs]
        async with AsyncSessionLocal() as session:
            balances = dict(
                (
                    await session.execute(
                        select(Resource.user_id, Resource.coin).where(
                            Resource.user_id.in_(ids)
                        )
                    )
                ).all()
            )
            assert sum(balances.values()) == 20_000
            assert all(
                balances[first] == 90 and balances[second] == 110
                for first, second in pairs
            )
    finally:
        await _cleanup(tuple(ids))


@pytest.mark.asyncio
async def test_parallel_invites_and_accepts_allow_one_live_game_per_user() -> None:
    ids = await _players(31)
    shared, contenders = ids[0], ids[1:]

    async def invite(contender: int) -> int | None:
        async with AsyncSessionLocal() as session:
            try:
                game = await create_game(session, shared, contender, "friendly")
                await session.commit()
                return game.id
            except GameError:
                await session.rollback()
                return None

    async def accept(game_id: int, contender: int) -> bool:
        async with AsyncSessionLocal() as session:
            try:
                await accept_game(session, game_id, contender)
                await session.commit()
                return True
            except GameError:
                await session.rollback()
                return False

    try:
        results = await asyncio.gather(*(invite(user_id) for user_id in contenders))
        game_ids = [game_id for game_id in results if game_id is not None]
        assert len(game_ids) == 1
        winner_contender = contenders[results.index(game_ids[0])]
        accepted = await asyncio.gather(
            *(accept(game_ids[0], winner_contender) for _ in range(10))
        )
        assert accepted.count(True) == 1
    finally:
        await _cleanup(tuple(ids))
