"""Deterministic road and Telegram sandbox limits."""

import zlib
from datetime import timedelta

import pytest

from app.bot.car_game_widget import HTML
from app.models.car_game import CarGame
from app.services import car_game_service
from app.services.car_game_service import advance_game, interval, now, road_event


def test_car_widget_fits_sandbox_and_uses_tap_requests() -> None:
    assert len(HTML.encode()) <= 32768
    assert len(zlib.compress(HTML.encode(), 9)) <= 4096
    assert "TelegramWidget" in HTML
    assert "requestAnimationFrame" in HTML
    assert "T.request('car:'" in HTML
    assert "touch-action:none" in HTML
    assert "fetch(" not in HTML
    assert '<canvas id="scene"' in HTML


def test_road_is_deterministic_and_faster_over_time() -> None:
    assert road_event(1, 4) == ("obstacle", 1, 0b010)
    assert road_event(1, 15) == ("obstacle", 2, 0b101)
    assert road_event(1, 4) == road_event(1, 4)
    assert interval(0) == 1.25
    assert interval(42) == 0.83
    assert interval(1000) == 0.62


@pytest.mark.asyncio
async def test_second_barrier_lane_causes_a_crash() -> None:
    started = now() - timedelta(seconds=10)
    game = CarGame(
        id=1,
        user_id=1,
        status="active",
        seed=1,
        lane=0,
        tick=15,
        coin=0,
        diamond=0,
        started_at=started,
        next_tick_at=started + timedelta(seconds=1),
    )
    assert await advance_game(None, game, moment=now())
    assert game.status == "crashed"


@pytest.mark.asyncio
async def test_rewards_never_exceed_play_time_rate(monkeypatch) -> None:
    started = now()
    game = CarGame(
        id=1,
        user_id=1,
        status="active",
        seed=1,
        lane=1,
        tick=0,
        coin=0,
        diamond=0,
        started_at=started,
        next_tick_at=started + timedelta(seconds=interval(0)),
    )
    monkeypatch.setattr(
        car_game_service,
        "road_event",
        lambda _seed, tick: ("coin" if tick % 2 == 0 else "diamond", 1, 0),
    )
    await advance_game(None, game, moment=started + timedelta(minutes=1))
    assert game.coin <= 50
    assert game.diamond <= 10
    assert game.coin > 0 and game.diamond > 0
