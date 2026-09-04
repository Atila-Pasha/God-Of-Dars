from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AttackStatus, ResourceType, TeacherStatus
from app.core.game_logic import GameConfig, game_config
from app.models.attack import Attack
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.repositories.castle import CastleRepository
from app.repositories.teacher import TeacherRepository
from app.repositories.user import UserRepository
from app.services.castle_service import CastleService
from app.services.school_errors import (
    InvalidTeacherState,
    SchoolUserNotFound,
    TeacherInHospital,
    TeacherNotOwned,
)
from app.services.teacher_service import TeacherService


@dataclass(frozen=True)
class AttackResult:
    attack: Attack
    attacker_name: str
    target_name: str
    target_telegram_id: int
    teacher_name: str
    ability_text: str | None
    castle_damage: int
    teacher_injury: int
    castle_strength_after: int
    loot_coin: int
    loot_diamond: int
    loot_banana: int


@dataclass(frozen=True)
class AttackPreview:
    attacker_id: int
    target_id: int
    teacher_id: int
    attacker_name: str
    target_name: str
    teacher_name: str
    ability_text: str | None
    teacher_damage: int
    defense_power: int
    estimated_castle_damage: int
    estimated_teacher_injury: int
    loot_coin: int
    loot_diamond: int
    loot_banana: int


class AttackService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config
        self.users = UserRepository()
        self.teachers = TeacherRepository()
        self.castles = CastleRepository()
        self.teacher_service = TeacherService(self.teachers, config=self.config)
        self.castle_service = CastleService(self.castles, config=self.config)

    async def attack_by_username(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_username: str,
        teacher_name: str,
    ) -> AttackResult:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        if attacker is None or not attacker.is_active:
            raise SchoolUserNotFound
        target = await self.users.get_active_by_username(
            session, target_username, for_update=True
        )
        if target is None:
            raise SchoolUserNotFound
        return await self._attack(session, attacker, target, teacher_name)

    async def preview_by_username(
        self, session: AsyncSession, *, attacker_telegram_id: int,
        target_username: str, teacher_name: str,
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(session, attacker_telegram_id)
        target = await self.users.get_active_by_username(session, target_username)
        if attacker is None or target is None or not attacker.is_active:
            raise SchoolUserNotFound
        return await self._preview(session, attacker, target, teacher_name)

    async def attack_by_telegram_id(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_telegram_id: int,
        teacher_name: str,
    ) -> AttackResult:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        target = await self.users.get_by_telegram_user_id(
            session, target_telegram_id, for_update=True
        )
        if (
            attacker is None
            or target is None
            or not attacker.is_active
            or not target.is_active
        ):
            raise SchoolUserNotFound
        return await self._attack(session, attacker, target, teacher_name)

    async def preview_by_telegram_id(
        self, session: AsyncSession, *, attacker_telegram_id: int,
        target_telegram_id: int, teacher_name: str,
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(session, attacker_telegram_id)
        target = await self.users.get_by_telegram_user_id(session, target_telegram_id)
        if attacker is None or target is None or not attacker.is_active or not target.is_active:
            raise SchoolUserNotFound
        return await self._preview(session, attacker, target, teacher_name)

    async def attack_by_ids(
        self, session: AsyncSession, *, attacker_telegram_id: int,
        target_id: int, teacher_id: int,
    ) -> AttackResult:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        target = await self.users.get_active_by_id(session, target_id, for_update=True)
        if attacker is None or target is None or not attacker.is_active:
            raise SchoolUserNotFound
        teacher = await self.teachers.get_owned_for_update(session, attacker.id, teacher_id)
        if teacher is None:
            raise TeacherNotOwned
        return await self._attack_with_teacher(session, attacker, target, teacher)

    async def _preview(self, session, attacker, target, teacher_name: str) -> AttackPreview:
        teacher = await self.teachers.get_owned_by_name_for_update(
            session, attacker.id, teacher_name
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.status is TeacherStatus.RECOVERING:
            raise TeacherInHospital
        if teacher.status is not TeacherStatus.ACTIVE:
            raise InvalidTeacherState
        if teacher.current_hp <= 0:
            teacher.current_hp = 0
            teacher.status = TeacherStatus.DISABLED
            raise InvalidTeacherState
        castle = await self.castle_service.battle_snapshot(session, target.id)
        damage, injury = self.config.attack_rules.resolve(
            self.teacher_service.damage(teacher), castle.defense_power, teacher.current_hp
        )
        loot = self._loot(target, damage, castle.strength)
        return AttackPreview(
            # The confirmation callback is clicked by Telegram and therefore
            # must carry the Telegram id, not the database user id.
            attacker_id=attacker.telegram_user_id,
            target_id=target.id,
            teacher_id=teacher.id,
            attacker_name=attacker.first_name, target_name=target.first_name,
            teacher_name=teacher.teacher.name,
            ability_text=teacher.teacher.ability_text,
            teacher_damage=self.teacher_service.damage(teacher),
            defense_power=castle.defense_power, estimated_castle_damage=damage,
            estimated_teacher_injury=injury, **loot,
        )

    async def _attack(self, session, attacker, target, teacher_name: str) -> AttackResult:
        if attacker.id == target.id:
            raise SchoolUserNotFound
        teacher = await self.teachers.get_owned_by_name_for_update(
            session, attacker.id, teacher_name
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.status is TeacherStatus.RECOVERING:
            raise TeacherInHospital
        if teacher.status is not TeacherStatus.ACTIVE:
            raise InvalidTeacherState

        return await self._attack_with_teacher(session, attacker, target, teacher)

    async def _attack_with_teacher(self, session, attacker, target, teacher) -> AttackResult:
        if teacher.status is TeacherStatus.RECOVERING:
            raise TeacherInHospital
        if teacher.status is not TeacherStatus.ACTIVE:
            raise InvalidTeacherState
        if teacher.current_hp <= 0:
            teacher.current_hp = 0
            teacher.status = TeacherStatus.DISABLED
            raise InvalidTeacherState
        await session.execute(
            select(Resource)
            .where(Resource.user_id.in_((attacker.id, target.id)))
            .with_for_update()
        )
        teacher_damage = self.teacher_service.damage(teacher)
        target_castle = await self.castle_service.battle_snapshot(session, target.id)
        pre_shield_damage, teacher_injury = self.config.attack_rules.resolve(
            teacher_damage, target_castle.defense_power, teacher.current_hp
        )
        castle_damage_result = await self.castle_service.receive_attack_damage(
            session, target.id, pre_shield_damage
        )
        if teacher_injury:
            teacher.current_hp = max(0, teacher.current_hp - teacher_injury)
            # Taking damage does not send an otherwise usable teacher to the
            # hospital.  The owner can do that explicitly from the teachers
            # screen; reaching zero is the only automatic hospitalization.
            if teacher.current_hp == 0:
                teacher.status = TeacherStatus.DISABLED

        loot = self._loot(
            target, castle_damage_result.applied_damage, target_castle.strength
        )
        self._transfer_loot(session, attacker, target, loot)

        now = datetime.now(UTC)
        attack = Attack(
            attacker_id=attacker.id,
            target_id=target.id,
            teacher_id=teacher.id,
            status=AttackStatus.RESOLVED,
            resolve_at=now,
            resolved_at=now,
            teacher_damage_snapshot=teacher_damage,
            target_castle_strength_snapshot=target_castle.strength,
            target_defense_power_snapshot=target_castle.defense_power,
            result_damage=castle_damage_result.applied_damage,
            loot_coin=loot["loot_coin"],
            loot_diamond=loot["loot_diamond"],
            loot_banana=loot["loot_banana"],
            is_successful=castle_damage_result.applied_damage > 0,
        )
        session.add(attack)
        await session.flush()
        return AttackResult(
            attack=attack,
            attacker_name=attacker.first_name,
            target_name=target.first_name,
            target_telegram_id=target.telegram_user_id,
            teacher_name=teacher.teacher.name,
            ability_text=teacher.teacher.ability_text,
            castle_damage=castle_damage_result.applied_damage,
            teacher_injury=teacher_injury,
            castle_strength_after=castle_damage_result.castle_strength_after,
            **loot,
        )

    def _loot(self, target, castle_damage: int, castle_strength: int) -> dict[str, int]:
        if castle_damage <= 0 or target.resources is None:
            return {"loot_coin": 0, "loot_diamond": 0, "loot_banana": 0}
        damage_factor = min(1.0, castle_damage / max(1, castle_strength))
        percent = self.config.attack_rules.loot_percent / 100 * damage_factor
        return {
            "loot_coin": min(target.resources.coin, int(target.resources.coin * percent)),
            "loot_diamond": min(target.resources.diamond, int(target.resources.diamond * percent)),
            "loot_banana": min(target.resources.banana, int(target.resources.banana * percent)),
        }

    @staticmethod
    def _transfer_loot(session, attacker, target, loot: dict[str, int]) -> None:
        if attacker.resources is None or target.resources is None:
            return
        for resource_type in ResourceType:
            key = f"loot_{resource_type.value.lower()}"
            amount = loot[key]
            if amount <= 0:
                continue
            field = resource_type.value.lower()
            target_before = getattr(target.resources, field)
            attacker_before = getattr(attacker.resources, field)
            setattr(target.resources, field, target_before - amount)
            setattr(attacker.resources, field, attacker_before + amount)
            session.add(Transaction(
                user_id=target.id, resource_type=resource_type, amount=-amount,
                balance_before=target_before, balance_after=target_before - amount,
                reason="ATTACK_LOOT", reference_type="ATTACK",
            ))
            session.add(Transaction(
                user_id=attacker.id, resource_type=resource_type, amount=amount,
                balance_before=attacker_before, balance_after=attacker_before + amount,
                reason="ATTACK_LOOT", reference_type="ATTACK",
            ))
