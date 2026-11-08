"""Server-authoritative lane changes, road events and one-time payouts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from secrets import randbelow

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.car_game import CarGame
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User


class CarGameError(ValueError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def interval(tick: int) -> float:
    """Increase traffic speed steadily, with a playable 0.62-second floor."""
    return max(0.62, round(1.25 - 0.07 * (tick // 7), 2))


def road_event(seed: int, tick: int) -> tuple[str, int, int]:
    """Return item, lane and obstacle bitmask from the shared integer hash."""
    value = (seed * 48271 + tick * 16807) % 1_000_003
    value = (value * 69621 + 12345) % 1_000_003
    lane = value // 100 % 3
    if tick < 2:
        return "coin", lane, 0
    roll = value % 100
    obstacle_chance = min(65, 33 + tick // 5)
    if roll < obstacle_chance:
        blocked = 1 << lane
        if tick % 3 == 0 and value // 1000 % 100 < 80:
            second_lane = (lane + 1 + value // 10_000 % 2) % 3
            blocked |= 1 << second_lane
        return "obstacle", lane, blocked
    if roll < obstacle_chance + 25:
        return "coin", lane, 0
    if roll < obstacle_chance + 34:
        return "diamond", lane, 0
    return "empty", lane, 0


def state_json(game: CarGame, *, timestamp: datetime | None = None) -> str:
    moment = timestamp or now()
    return json.dumps(
        {
            "id": game.id,
            "status": game.status,
            "seed": game.seed,
            "lane": game.lane,
            "tick": game.tick,
            "coin": game.coin,
            "diamond": game.diamond,
            "start_ms": int(game.started_at.timestamp() * 1000)
            if game.started_at
            else 0,
            "server_ms": int(moment.timestamp() * 1000),
        },
        separators=(",", ":"),
    )


async def create_game(session: AsyncSession, user_id: int) -> CarGame:
    await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
    active = await session.scalar(
        select(CarGame.id).where(CarGame.user_id == user_id, CarGame.status == "active")
    )
    if active is not None:
        raise CarGameError("اول بازی ماشین فعلی رو تموم کن.")
    await session.execute(
        update(CarGame)
        .where(CarGame.user_id == user_id, CarGame.status == "ready")
        .values(status="cancelled")
    )
    game = CarGame(
        user_id=user_id,
        status="ready",
        seed=randbelow(1_000_000),
        lane=1,
        tick=0,
        coin=0,
        diamond=0,
    )
    session.add(game)
    await session.flush()
    return game


async def _credit_rewards(session: AsyncSession, game: CarGame) -> None:
    if not game.coin and not game.diamond:
        return
    resources = await session.scalar(
        select(Resource)
        .where(Resource.user_id == game.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resources is None:
        raise CarGameError("حساب بازی پیدا نشد.")
    for kind, amount, field in (
        (ResourceType.COIN, game.coin, "coin"),
        (ResourceType.DIAMOND, game.diamond, "diamond"),
    ):
        if not amount:
            continue
        before = getattr(resources, field)
        setattr(resources, field, before + amount)
        session.add(
            Transaction(
                user_id=game.user_id,
                resource_type=kind,
                amount=amount,
                balance_before=before,
                balance_after=before + amount,
                reason="car_game_reward",
                reference_type="car_game",
                reference_id=game.id,
            )
        )


async def advance_game(
    session: AsyncSession, game: CarGame, *, moment: datetime | None = None
) -> bool:
    """Settle due road items; return whether this call caused a crash."""
    current = moment or now()
    if game.status != "active":
        return False
    started_at = game.started_at
    if started_at is None:
        raise CarGameError("زمان شروع بازی ثبت نشده است.")
    for _ in range(128):
        if game.status != "active" or game.next_tick_at is None:
            break
        if game.next_tick_at > current:
            break
        due = game.next_tick_at
        item, lane, blocked = road_event(game.seed, game.tick)
        elapsed = max(0, (due - started_at).total_seconds())
        if blocked & (1 << game.lane):
            game.status = "crashed"
            game.next_tick_at = None
            await _credit_rewards(session, game)
            return True
        if lane == game.lane:
            if item == "coin":
                game.coin = min(game.coin + 1, int(elapsed * 50 / 60))
            elif item == "diamond":
                game.diamond = min(game.diamond + 1, int(elapsed * 10 / 60))
        game.tick += 1
        game.next_tick_at = due + timedelta(seconds=interval(game.tick))
    return False


async def act(
    session: AsyncSession,
    game_id: int,
    user_id: int,
    message_id: int,
    action: str,
) -> tuple[CarGame, bool]:
    game = await session.scalar(
        select(CarGame)
        .where(CarGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None or game.user_id != user_id or game.message_id != message_id:
        raise CarGameError("پیام بازی معتبر نیست.")
    if action == "start":
        if game.status == "ready":
            game.status = "active"
            game.started_at = now()
            game.next_tick_at = game.started_at + timedelta(seconds=interval(0))
        elif game.status != "active":
            raise CarGameError("این بازی تموم شده؛ از /game بازی تازه شروع کن.")
        return game, False
    if action not in {"left", "right", "sync", "lane0", "lane1", "lane2"}:
        raise CarGameError("حرکت معتبر نیست.")
    crashed = await advance_game(session, game)
    if game.status == "active" and action != "sync":
        target = (
            int(action[-1])
            if action.startswith("lane")
            else game.lane + (-1 if action == "left" else 1)
        )
        if abs(target - game.lane) > 1:
            raise CarGameError("تغییر لاین معتبر نیست.")
        game.lane = max(0, min(2, target))
    return game, crashed


async def settle_due_game(session: AsyncSession, game_id: int) -> CarGame | None:
    game = await session.scalar(
        select(CarGame)
        .where(CarGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None or game.status != "active":
        return None
    return game if await advance_game(session, game) else None
