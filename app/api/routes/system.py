from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.api.dependencies import DatabaseSession
from app.core.game_logic import game_config

health_router = APIRouter(tags=["health"])
meta_router = APIRouter(prefix="/meta", tags=["metadata"])
config_router = APIRouter(tags=["metadata"])


@health_router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@health_router.get("/health/ready")
async def ready(session: DatabaseSession) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@meta_router.get("")
async def metadata(response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=60"
    return {
        "api_version": "v1",
        "minimum_app_version": None,
        "maintenance": False,
        "server_time": datetime.now(UTC),
    }


@config_router.get("/game-config")
async def public_game_config(response: Response) -> dict:
    payload = {
        "max_attack_teachers": game_config.max_attack_teachers,
        "max_player_level": game_config.level_progression.max_level,
        "max_teacher_level": game_config.teacher_max_level,
        "max_mine_level": game_config.mine_max_level,
        "mine_max_catchup_minutes": game_config.mine_max_catchup_minutes,
        "teacher_ownership_limit": game_config.ownership_limit,
    }
    tag = hashlib.sha256(repr(sorted(payload.items())).encode()).hexdigest()
    response.headers["ETag"] = f'"{tag}"'
    response.headers["Cache-Control"] = "public, max-age=300"
    return payload
