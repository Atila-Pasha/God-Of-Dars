"""Chess rules and wager settlement against the local PostgreSQL database."""

from uuid import uuid4

import chess
import pytest
from sqlalchemy import delete, select

from app.bot.chess_widget import HTML, state_json
from app.db.session import AsyncSessionLocal
from app.models.chess_game import ChessGame
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User
from app.services.chess_service import (
    ChessError,
    accept_game,
    board_for,
    computer_move,
    create_game,
    move,
)


def test_widget_and_chess_rules() -> None:
    assert "TelegramWidget" in HTML
    assert "chatDataChanged" in HTML
    board = chess.Board()
    board.push_uci("e2e4")
    reply = computer_move(board)
    assert reply in board.legal_moves
    board.push(reply)
    assert board.is_valid()
    game = ChessGame(moves="g1f3 g8f6 f3g1 f6g8 " * 2)
    assert board_for(game).can_claim_threefold_repetition()


@pytest.mark.asyncio
async def test_chess_wager_invite_moves_and_checkmate() -> None:
    ids = [int(uuid4().int % 2_000_000_000) for _ in range(2)]
    async with AsyncSessionLocal() as session:
        players = [
            User(
                telegram_user_id=tg_id,
                first_name=f"chess test {i}",
                resources=Resource(coin=100, diamond=10),
            )
            for i, tg_id in enumerate(ids)
        ]
        session.add_all(players)
        await session.commit()
        user_ids = [p.id for p in players]
    game_id = None
    try:
        async with AsyncSessionLocal() as session:
            game = await create_game(
                session, user_ids[0], user_ids[1], "wager", "coin", 10
            )
            game_id = game.id
            await session.commit()
            assert game.status == "invited"
            game = await accept_game(session, game_id, user_ids[1])
            assert game.status == "active" and game.escrowed
            await session.commit()

        async with AsyncSessionLocal() as session:
            with pytest.raises(ChessError, match="نوبت"):
                await move(session, game_id, user_ids[1], "e7e5")
            with pytest.raises(ChessError, match="قانونی"):
                await move(session, game_id, user_ids[0], "e2e5")
            for actor, uci in (
                (user_ids[0], "f2f3"),
                (user_ids[1], "e7e5"),
                (user_ids[0], "g2g4"),
                (user_ids[1], "d8h4"),
            ):
                game = await move(session, game_id, actor, uci)
                await session.commit()
            assert game.status == "finished"
            assert game.winner_id == user_ids[1]
            assert board_for(game).is_checkmate()
            assert len(state_json(game, *ids).encode()) <= 1024
            with pytest.raises(ChessError, match="تموم"):
                await move(session, game_id, user_ids[0], "e2e4")

        async with AsyncSessionLocal() as session:
            resources = (
                await session.scalars(
                    select(Resource).where(Resource.user_id.in_(user_ids))
                )
            ).all()
            balances = {r.user_id: r.coin for r in resources}
            assert balances == {user_ids[0]: 90, user_ids[1]: 110}
            entries = (
                await session.scalars(
                    select(Transaction).where(
                        Transaction.reference_type == "chess",
                        Transaction.reference_id == game_id,
                    )
                )
            ).all()
            assert sorted(e.amount for e in entries) == [-10, -10, 20]
    finally:
        async with AsyncSessionLocal() as session:
            if game_id is not None:
                await session.execute(
                    delete(Transaction).where(
                        Transaction.reference_type == "chess",
                        Transaction.reference_id == game_id,
                    )
                )
                await session.execute(delete(ChessGame).where(ChessGame.id == game_id))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.commit()
