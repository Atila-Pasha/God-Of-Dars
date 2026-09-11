from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import exists, func, or_, select

from app.api.cursors import CursorCodec
from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.errors import APIError
from app.api.presenters import battle, battle_preview
from app.api.responses import idempotent_response
from app.api.schemas.domain import (
    BattleLaunchView,
    BattlePage,
    BattlePreviewRequest,
    BattlePreviewView,
    BattleStartRequest,
    BattleView,
    OpponentView,
)
from app.core.enums import AttackStatus
from app.models.attack import Attack
from app.models.user import User
from app.models.user_shield import UserShield
from app.services.attack_service import AttackService
from app.services.teacher_service import TeacherService

router = APIRouter(prefix="/battles", tags=["battles"])
attacks = AttackService()
teachers = TeacherService()


async def _selection(
    session: DatabaseSession, user_id: int, teacher_ids: list[int]
) -> tuple[list[int], list[str]]:
    unique_ids = list(dict.fromkeys(teacher_ids))
    if len(unique_ids) != len(teacher_ids):
        raise APIError(400, "DUPLICATE_TEACHER", "هر دبیر فقط یک بار قابل انتخاب است.")
    if len(unique_ids) > attacks.config.max_attack_teachers:
        raise APIError(
            400, "TOO_MANY_TEACHERS", "تعداد دبیرهای انتخابی بیش از حد مجاز است."
        )
    owned = [
        await teachers.get_owned(session, user_id, item_id) for item_id in unique_ids
    ]
    return unique_ids, [item.teacher.name for item in owned]


@router.get("/opponents", response_model=list[OpponentView])
async def opponents(
    current: AuthenticatedUser,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[OpponentView]:
    level_distance = 5
    rows = list(
        (
            await session.scalars(
                select(User)
                .where(
                    User.is_active.is_(True),
                    User.id != current.user.id,
                    User.level.between(
                        max(1, current.user.level - level_distance),
                        current.user.level + level_distance,
                    ),
                    ~exists(
                        select(UserShield.id).where(
                            UserShield.user_id == User.id,
                            UserShield.is_equipped.is_(True),
                            UserShield.active_until.is_not(None),
                            UserShield.active_until > func.now(),
                        )
                    ),
                )
                .order_by(User.level, User.id)
                .limit(limit)
            )
        ).all()
    )
    return [
        OpponentView(
            id=item.id,
            username=item.username,
            name=" ".join(part for part in (item.first_name, item.last_name) if part),
            level=item.level,
        )
        for item in rows
    ]


@router.post("/preview", response_model=BattlePreviewView)
async def preview_battle(
    body: BattlePreviewRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
) -> BattlePreviewView:
    _, names = await _selection(session, current.user.id, body.teacher_ids)
    target = await session.scalar(
        select(User).where(User.id == body.target_user_id, User.is_active.is_(True))
    )
    if target is None:
        raise APIError(404, "TARGET_NOT_AVAILABLE", "حریف در دسترس نیست.")
    result = await attacks.preview_by_telegram_id(
        session,
        attacker_telegram_id=current.user.telegram_user_id,
        target_telegram_id=target.telegram_user_id,
        teacher_name=names,
    )
    return battle_preview(result, names, attacker_user_id=current.user.id)


@router.post("", response_model=BattleLaunchView, status_code=202)
async def start_battle(
    body: BattleStartRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> BattleLaunchView:
        unique_ids, names = await _selection(session, current.user.id, body.teacher_ids)
        launch = await attacks.start_attack_by_ids(
            session,
            attacker_telegram_id=current.user.telegram_user_id,
            target_id=body.target_user_id,
            teacher_ids=unique_ids,
        )
        if not launch.attack_ids:
            raise APIError(500, "BATTLE_CREATION_FAILED", "حمله ثبت نشد.")
        return BattleLaunchView(
            battle_ids=list(launch.attack_ids),
            status=AttackStatus.PENDING.value,
            target_name=launch.target_name,
            teacher_names=names,
            resolve_at=launch.resolve_at,
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="battle.start",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
        action=action,
        status_code=202,
    )


@router.get("/{battle_id}", response_model=BattleView)
async def battle_status(
    battle_id: int, current: AuthenticatedUser, session: DatabaseSession
) -> BattleView:
    item = await session.scalar(
        select(Attack).where(
            Attack.id == battle_id,
            or_(
                Attack.attacker_id == current.user.id,
                Attack.target_id == current.user.id,
            ),
        )
    )
    if item is None:
        raise APIError(404, "BATTLE_NOT_FOUND", "نبرد پیدا نشد.")
    return battle(item)


@router.get("", response_model=BattlePage)
async def battle_history(
    current: AuthenticatedUser,
    session: DatabaseSession,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    direction: Annotated[str, Query(pattern="^(all|sent|received)$")] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> BattlePage:
    before_id = CursorCodec.decode(cursor, resource=f"battles:{direction}")
    ownership = {
        "all": or_(
            Attack.attacker_id == current.user.id,
            Attack.target_id == current.user.id,
        ),
        "sent": Attack.attacker_id == current.user.id,
        "received": Attack.target_id == current.user.id,
    }[direction]
    query = select(Attack).where(ownership)
    if before_id is not None:
        query = query.where(Attack.id < before_id)
    rows = list(
        (await session.scalars(query.order_by(Attack.id.desc()).limit(limit + 1))).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return BattlePage(
        items=[battle(item) for item in rows],
        next_cursor=(
            CursorCodec.encode(resource=f"battles:{direction}", last_id=rows[-1].id)
            if has_more and rows
            else None
        ),
    )
