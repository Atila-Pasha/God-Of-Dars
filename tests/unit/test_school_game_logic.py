from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import TeacherStatus
from app.core.game_logic import CastleRepairRules, CastleUpgrade, GameConfig
from app.models.castle import Castle
from app.models.defense import Defense
from app.models.recovery import Recovery
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.services.castle_service import CastleService
from app.services.recovery_service import HospitalService
from app.services.school_errors import (
    InsufficientCoins,
    TeacherLocked,
    TeacherSlotLocked,
)
from app.services.teacher_service import TeacherService


class FakeTeacherRepository:
    def __init__(self, *, user, resources, teacher, owned=None, owned_count=0):
        self.user = user
        self.resources = resources
        self.teacher = teacher
        self.owned = owned
        self.owned_count = owned_count

    async def get_user(self, session, user_id):
        return self.user

    async def get_user_for_update(self, session, user_id):
        return self.user

    async def get_resources_for_update(self, session, user_id):
        return self.resources

    async def count_owned(self, session, user_id):
        return self.owned_count

    async def get_catalog_teacher(self, session, teacher_id):
        return self.teacher

    async def get_owned_by_teacher_for_update(self, session, user_id, teacher_id):
        return None

    async def get_owned_for_update(self, session, user_id, user_teacher_id):
        return self.owned

    async def list_owned(self, session, user_id):
        return [self.owned] if self.owned is not None else []


class FakeCastleRepository:
    def __init__(self, *, user, resources, castle):
        self.user = user
        self.resources = resources
        self.castle = castle

    async def get_user_for_update(self, session, user_id):
        return self.user

    async def get_resources_for_update(self, session, user_id):
        return self.resources

    async def get_by_user(self, session, user_id, *, for_update=False):
        return self.castle


def user(level: int = 1) -> User:
    return User(
        id=10,
        telegram_user_id=42,
        first_name="Ali",
        level=level,
    )


def teacher(**overrides) -> Teacher:
    values = {
        "id": 7,
        "name": "قاضی",
        "damage": 10,
        "max_hp": 100,
        "purchase_price": 40,
        "upgrade_price": 30,
        "unlock_level": 1,
        "is_active": True,
    }
    values.update(overrides)
    return Teacher(**values)


def owned_teacher(model: Teacher) -> UserTeacher:
    return UserTeacher(
        id=11,
        user_id=10,
        teacher_id=model.id,
        level=1,
        current_hp=73,
        status=TeacherStatus.ACTIVE,
        teacher=model,
    )


@pytest.mark.asyncio
async def test_level_capacity_is_configurable_and_clamped() -> None:
    config = GameConfig(
        max_teacher_slots=4,
        teacher_slots_by_level=((1, 1), (5, 3), (10, 4)),
    )

    assert config.teacher_slots(1) == 1
    assert config.teacher_slots(7) == 3
    assert config.teacher_slots(10) == 4


@pytest.mark.asyncio
async def test_buy_teacher_enforces_level_slot_capacity_and_charges_atomically() -> (
    None
):
    model = teacher()
    repository = FakeTeacherRepository(
        user=user(level=1),
        resources=SimpleNamespace(coin=100, diamond=0),
        teacher=model,
        owned_count=0,
    )
    session = SimpleNamespace(add=lambda item: None, flush=AsyncMock())
    service = TeacherService(
        repository,
        config=GameConfig(teacher_slots_by_level=((1, 1),)),
    )

    result = await service.buy(session, 10, model.id)

    assert result.teacher is model
    assert repository.resources.coin == 60
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_buy_teacher_rejects_locked_slot_before_purchase() -> None:
    model = teacher()
    repository = FakeTeacherRepository(
        user=user(level=1),
        resources=SimpleNamespace(coin=100, diamond=0),
        teacher=model,
        owned_count=1,
    )
    service = TeacherService(
        repository,
        config=GameConfig(teacher_slots_by_level=((1, 1), (5, 3))),
    )

    with pytest.raises(TeacherSlotLocked):
        await service.buy(SimpleNamespace(), 10, model.id)


@pytest.mark.asyncio
async def test_teacher_unlock_level_is_independent_from_slot_capacity() -> None:
    model = teacher(unlock_level=10)
    repository = FakeTeacherRepository(
        user=user(level=5),
        resources=SimpleNamespace(coin=0, diamond=100),
        teacher=model,
        owned_count=0,
    )
    service = TeacherService(
        repository,
        config=GameConfig(teacher_slots_by_level=((1, 3),)),
    )

    with pytest.raises(TeacherLocked):
        await service.buy(SimpleNamespace(), 10, model.id)


@pytest.mark.asyncio
async def test_upgrade_changes_damage_and_preserves_hp() -> None:
    model = teacher()
    owned = owned_teacher(model)
    repository = FakeTeacherRepository(
        user=user(),
        resources=SimpleNamespace(coin=0, diamond=100),
        teacher=model,
        owned=owned,
    )
    service = TeacherService(
        repository,
        config=GameConfig(
            teacher_damage_by_level={(model.id, 2): 25},
        ),
    )

    await service.upgrade(
        SimpleNamespace(add=lambda item: None, flush=AsyncMock()), 10, 11
    )

    assert owned.level == 2
    assert owned.current_hp == 73
    assert service.damage(owned) == 25
    assert repository.resources.diamond == 70


@pytest.mark.asyncio
async def test_upgrade_rejects_insufficient_diamonds_without_changing_teacher() -> None:
    model = teacher()
    owned = owned_teacher(model)
    repository = FakeTeacherRepository(
        user=user(),
        resources=SimpleNamespace(coin=100, diamond=29),
        teacher=model,
        owned=owned,
    )
    service = TeacherService(
        repository,
        config=GameConfig(teacher_damage_by_level={(model.id, 2): 25}),
    )

    with pytest.raises(InsufficientCoins):
        await service.upgrade(SimpleNamespace(), 10, 11)

    assert owned.level == 1
    assert owned.current_hp == 73


@pytest.mark.asyncio
async def test_castle_upgrade_changes_defense_and_deducts_diamonds() -> None:
    castle = Castle(
        id=3,
        user_id=10,
        level=1,
        strength=10,
        defense=Defense(defense_power=4),
    )
    repository = FakeCastleRepository(
        user=user(),
        resources=SimpleNamespace(coin=0, diamond=100),
        castle=castle,
    )
    service = CastleService(
        repository,
        config=GameConfig(
            castle_upgrade_by_level={
                1: CastleUpgrade(
                    diamond_cost=30,
                    strength_delta=5,
                    defense_delta=2,
                )
            }
        ),
    )
    session = SimpleNamespace(add=lambda item: None, flush=AsyncMock())

    await service.upgrade(session, 10)

    assert castle.level == 2
    assert castle.strength == 15
    assert castle.defense.defense_power == 6
    assert repository.resources.diamond == 70


@pytest.mark.asyncio
async def test_castle_repair_scales_with_missing_strength_and_restores_health() -> None:
    castle = Castle(
        id=3,
        user_id=10,
        level=1,
        strength=40,
        defense=Defense(defense_power=4),
    )
    repository = FakeCastleRepository(
        user=user(),
        resources=SimpleNamespace(coin=0, diamond=10),
        castle=castle,
    )
    service = CastleService(
        repository,
        config=GameConfig(
            initial_castle_strength=100,
            castle_repair=CastleRepairRules(
                diamond_cost_per_100_strength=5,
                minimum_diamond_cost=1,
            ),
        ),
    )
    session = SimpleNamespace(add=lambda item: None, flush=AsyncMock())

    await service.repair(session, 10)

    assert castle.strength == 100
    assert repository.resources.diamond == 7


@pytest.mark.asyncio
async def test_hospital_completes_due_recovery_without_teacher_death() -> None:
    model = teacher()
    owned = UserTeacher(
        id=11,
        user_id=10,
        teacher_id=model.id,
        level=1,
        current_hp=20,
        status=TeacherStatus.RECOVERING,
        teacher=model,
    )
    owned.recoveries = [
        Recovery(
            user_teacher_id=owned.id,
            recovery_started_at=datetime.now(UTC) - timedelta(minutes=2),
            recovery_end_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    ]
    repository = FakeTeacherRepository(
        user=user(),
        resources=SimpleNamespace(coin=0),
        teacher=model,
        owned=owned,
    )
    session = SimpleNamespace(flush=AsyncMock())
    service = HospitalService(repository)

    patients = await service.patients(session, 10)

    assert patients == []
    assert owned.status is TeacherStatus.ACTIVE
    assert owned.current_hp == model.max_hp
    session.flush.assert_awaited_once()
