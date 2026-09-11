from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.presenters import castle, mine, profile, study_state
from app.api.schemas.domain import BootstrapView
from app.services.castle_service import CastleService
from app.services.mine_service import MineService
from app.services.profile_service import ProfileService
from app.services.study_service import StudyService

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap", response_model=BootstrapView)
async def bootstrap(
    current: AuthenticatedUser, session: DatabaseSession
) -> BootstrapView:
    profile_snapshot = await ProfileService().snapshot(session, current.user.id)
    castle_model = await CastleService().get_or_create(session, current.user.id)
    mine_snapshot = await MineService().open(session, current.user.id)
    study = await StudyService().active(session, current.user.id, for_update=False)
    return BootstrapView(
        profile=profile(profile_snapshot),
        castle=castle(castle_model),
        mine=mine(mine_snapshot, player_level=current.user.level),
        study=study_state(study),
        server_time=datetime.now(UTC),
    )


@router.get("/sync", response_model=BootstrapView)
async def sync(current: AuthenticatedUser, session: DatabaseSession) -> BootstrapView:
    return await bootstrap(current, session)
