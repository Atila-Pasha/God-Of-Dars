from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.presenters import (
    castle,
    owned_shield,
    owned_teacher,
    resources,
    shield_catalog,
    teacher_catalog,
)
from app.api.responses import idempotent_response
from app.api.schemas.domain import (
    CastleView,
    OwnedShieldView,
    OwnedTeacherView,
    ShieldCatalogView,
    TeacherCatalogView,
    TeacherListView,
)
from app.models.resource import Resource
from app.services.castle_service import CastleService
from app.services.recovery_service import HospitalService
from app.services.shield_service import ShieldService
from app.services.teacher_service import TeacherService

router = APIRouter(tags=["school"])
teachers = TeacherService()
castles = CastleService()
shields = ShieldService()
hospital = HospitalService()


async def _owned_teacher(
    session: DatabaseSession, user_id: int, owned_teacher_id: int
) -> OwnedTeacherView:
    item = await teachers.get_owned(session, user_id, owned_teacher_id)
    return owned_teacher(item, teachers)


@router.get("/teachers/catalog", response_model=list[TeacherCatalogView])
async def teacher_catalog_route(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[TeacherCatalogView]:
    return [
        teacher_catalog(item)
        for item in await teachers.catalog(session, current.user.id)
        if item.unlock_level <= current.user.level
    ]


@router.get("/me/teachers", response_model=TeacherListView)
async def my_teachers(
    current: AuthenticatedUser, session: DatabaseSession
) -> TeacherListView:
    items = await teachers.owned(session, current.user.id)
    capacity = await teachers.capacity(session, current.user.id)
    return TeacherListView(
        items=[owned_teacher(item, teachers) for item in items],
        owned=capacity.owned,
        available=capacity.available,
        maximum=capacity.maximum,
    )


@router.get("/me/teachers/{owned_teacher_id}", response_model=OwnedTeacherView)
async def teacher_detail(
    owned_teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
) -> OwnedTeacherView:
    return await _owned_teacher(session, current.user.id, owned_teacher_id)


@router.post("/me/teachers/{teacher_id}/purchase", response_model=OwnedTeacherView)
async def purchase_teacher(
    teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> OwnedTeacherView:
        created = await teachers.buy(session, current.user.id, teacher_id)
        return await _owned_teacher(session, current.user.id, created.id)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="teacher.purchase",
        key=idempotency_key,
        payload={"teacher_id": teacher_id},
        action=action,
        status_code=201,
    )


@router.post("/me/teachers/{owned_teacher_id}/upgrade", response_model=OwnedTeacherView)
async def upgrade_teacher(
    owned_teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> OwnedTeacherView:
        await teachers.upgrade(session, current.user.id, owned_teacher_id)
        return await _owned_teacher(session, current.user.id, owned_teacher_id)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="teacher.upgrade",
        key=idempotency_key,
        payload={"owned_teacher_id": owned_teacher_id},
        action=action,
    )


@router.post("/me/teachers/{owned_teacher_id}/sell")
async def sell_teacher(
    owned_teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> dict:
        sale_price = await teachers.sell(session, current.user.id, owned_teacher_id)
        balance = await session.scalar(
            select(Resource).where(Resource.user_id == current.user.id)
        )
        return {"sale_price": sale_price, "resources": resources(balance)}

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="teacher.sell",
        key=idempotency_key,
        payload={"owned_teacher_id": owned_teacher_id},
        action=action,
    )


@router.post(
    "/me/teachers/{owned_teacher_id}/activate", response_model=OwnedTeacherView
)
async def activate_teacher(
    owned_teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> OwnedTeacherView:
        await teachers.activate(session, current.user.id, owned_teacher_id)
        return await _owned_teacher(session, current.user.id, owned_teacher_id)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="teacher.activate",
        key=idempotency_key,
        payload={"owned_teacher_id": owned_teacher_id},
        action=action,
    )


@router.get("/me/hospital", response_model=list[OwnedTeacherView])
async def hospital_patients(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[OwnedTeacherView]:
    return [
        owned_teacher(item, teachers)
        for item in await hospital.patients(session, current.user.id)
    ]


@router.post("/me/teachers/{owned_teacher_id}/recover", response_model=OwnedTeacherView)
async def recover_teacher(
    owned_teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> OwnedTeacherView:
        await hospital.begin_recovery(session, current.user.id, owned_teacher_id)
        return await _owned_teacher(session, current.user.id, owned_teacher_id)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="teacher.recover",
        key=idempotency_key,
        payload={"owned_teacher_id": owned_teacher_id},
        action=action,
    )


@router.post(
    "/me/teachers/{owned_teacher_id}/recover-instant",
    response_model=OwnedTeacherView,
)
async def recover_teacher_instantly(
    owned_teacher_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> OwnedTeacherView:
        await hospital.instant_recover(session, current.user.id, owned_teacher_id)
        return await _owned_teacher(session, current.user.id, owned_teacher_id)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="teacher.recover-instant",
        key=idempotency_key,
        payload={"owned_teacher_id": owned_teacher_id},
        action=action,
    )


@router.get("/me/castle", response_model=CastleView)
async def my_castle(current: AuthenticatedUser, session: DatabaseSession) -> CastleView:
    return castle(await castles.get_or_create(session, current.user.id))


@router.post("/me/castle/repair", response_model=CastleView)
async def repair_castle(
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> CastleView:
        return castle(await castles.repair(session, current.user.id))

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="castle.repair",
        key=idempotency_key,
        payload={},
        action=action,
    )


@router.post("/me/castle/upgrade", response_model=CastleView)
async def upgrade_castle(
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> CastleView:
        return castle(await castles.upgrade(session, current.user.id))

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="castle.upgrade",
        key=idempotency_key,
        payload={},
        action=action,
    )


@router.get("/shields/catalog", response_model=list[ShieldCatalogView])
async def shield_catalog_route(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[ShieldCatalogView]:
    return [
        shield_catalog(item)
        for item in await shields.catalog(session, player_level=current.user.level)
    ]


@router.get("/me/shields", response_model=list[OwnedShieldView])
async def my_shields(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[OwnedShieldView]:
    return [
        owned_shield(item)
        for item in await shields.list_owned(session, current.user.id)
    ]


@router.post("/me/shields/{shield_id}/purchase", response_model=OwnedShieldView)
async def purchase_shield(
    shield_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> OwnedShieldView:
        await shields.buy(session, current.user.id, shield_id)
        owned = await shields.list_owned(session, current.user.id)
        return owned_shield(next(item for item in owned if item.shield_id == shield_id))

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="shield.purchase",
        key=idempotency_key,
        payload={"shield_id": shield_id},
        action=action,
        status_code=201,
    )
