from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AttackStatus, ResourceType, TeacherStatus
from app.core.game_logic import GameConfig, game_config
from app.models.attack import Attack
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user_teacher import UserTeacher
from app.repositories.castle import CastleRepository
from app.repositories.teacher import TeacherRepository
from app.repositories.user import UserRepository
from app.services.castle_service import CastleService
from app.services.school_errors import (
    AttackInProgress,
    InvalidTeacherState,
    SchoolUserNotFound,
    TeacherInHospital,
    TeacherLimitReached,
    TeacherNotOwned,
)
from app.services.teacher_service import TeacherService


@dataclass(frozen=True)
class AttackResult:
    attack: Attack
    attacker_telegram_id: int
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
    teacher_ids: str = ""


@dataclass(frozen=True)
class AttackLaunch:
    target_name: str
    teacher_name: str
    teacher_stickers: tuple[str, ...]
    resolve_at: datetime


class AttackService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config
        self.users = UserRepository()
        self.teachers = TeacherRepository()
        self.castles = CastleRepository()
        self.teacher_service = TeacherService(self.teachers, config=self.config)
        self.castle_service = CastleService(self.castles, config=self.config)

    @staticmethod
    async def _claim_attack_xp(
        session: AsyncSession, *, attack_command_id: str | None, attack_id: int
    ) -> bool:
        """Atomically claim the single XP reward for one attack command."""
        if attack_command_id is None:
            statement = (
                update(Attack)
                .where(Attack.id == attack_id, Attack.attack_xp_awarded.is_(False))
                .values(attack_xp_awarded=True)
            )
        else:
            first_unawarded = (
                select(func.min(Attack.id))
                .where(
                    Attack.attack_command_id == attack_command_id,
                    Attack.attack_xp_awarded.is_(False),
                )
                .scalar_subquery()
            )
            statement = (
                update(Attack)
                .where(
                    Attack.id == first_unawarded,
                )
                .values(attack_xp_awarded=True)
            )
        result = await session.execute(statement)
        return result.rowcount == 1

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
        target_username: str, teacher_name: str | list[str],
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
        target_telegram_id: int, teacher_name: str | list[str],
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(session, attacker_telegram_id)
        target = await self.users.get_by_telegram_user_id(session, target_telegram_id)
        if attacker is None or target is None or not attacker.is_active or not target.is_active:
            raise SchoolUserNotFound
        return await self._preview(session, attacker, target, teacher_name)

    async def attack_by_ids(
        self, session: AsyncSession, *, attacker_telegram_id: int,
        target_id: int, teacher_id: int, teacher_ids: list[int] | None = None,
    ) -> AttackResult:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        target = await self.users.get_active_by_id(session, target_id, for_update=True)
        if attacker is None or target is None or not attacker.is_active:
            raise SchoolUserNotFound
        selected_ids = teacher_ids or [teacher_id]
        if len(dict.fromkeys(selected_ids)) > self.config.max_attack_teachers:
            raise TeacherLimitReached
        teachers = []
        for selected_id in dict.fromkeys(selected_ids):
            teacher = await self.teachers.get_owned_for_update(
                session, attacker.id, selected_id
            )
            if teacher is None:
                raise TeacherNotOwned
            teachers.append(teacher)
        return await self._attack_with_teachers(session, attacker, target, teachers)

    async def start_attack_by_ids(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_id: int,
        teacher_ids: list[int],
        duration: timedelta = timedelta(minutes=2),
    ) -> AttackLaunch:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        target = await self.users.get_active_by_id(session, target_id, for_update=True)
        if attacker is None or target is None or not attacker.is_active:
            raise SchoolUserNotFound

        active_attack = await session.scalar(
            select(Attack)
            .where(
                Attack.attacker_id == attacker.id,
                Attack.status == AttackStatus.PENDING,
            )
            .with_for_update()
        )
        if active_attack is not None:
            raise AttackInProgress

        selected_ids = list(dict.fromkeys(teacher_ids))
        if not selected_ids:
            raise TeacherNotOwned
        if len(selected_ids) > self.config.max_attack_teachers:
            raise TeacherLimitReached
        teachers = []
        for selected_id in selected_ids:
            teacher = await self.teachers.get_owned_for_update(
                session, attacker.id, selected_id
            )
            if teacher is None:
                raise TeacherNotOwned
            if teacher.status is TeacherStatus.RECOVERING:
                raise TeacherInHospital
            if teacher.status is not TeacherStatus.ACTIVE or teacher.current_hp <= 0:
                raise InvalidTeacherState
            teachers.append(teacher)

        castle = await self.castle_service.battle_snapshot(session, target.id)
        resolve_at = datetime.now(UTC) + duration
        attack_command_id = str(uuid4())
        for teacher in teachers:
            session.add(
                Attack(
                    attacker_id=attacker.id,
                    target_id=target.id,
                    teacher_id=teacher.id,
                    status=AttackStatus.PENDING,
                    resolve_at=resolve_at,
                    attack_command_id=attack_command_id,
                    teacher_damage_snapshot=self.teacher_service.damage(teacher),
                    target_castle_strength_snapshot=castle.strength,
                    target_defense_power_snapshot=castle.defense_power,
                )
            )
        await session.flush()
        return AttackLaunch(
            target_name=target.first_name,
            teacher_name="، ".join(teacher.teacher.name for teacher in teachers),
            teacher_stickers=tuple(
                teacher.teacher.sticker
                for teacher in teachers
                if teacher.teacher.sticker
            ),
            resolve_at=resolve_at,
        )

    async def resolve_pending_attack(
        self, session: AsyncSession, attack_id: int
    ) -> AttackResult | None:
        attack = await session.scalar(
            select(Attack).where(
                Attack.id == attack_id,
                Attack.status == AttackStatus.PENDING,
            ).with_for_update()
        )
        if attack is None:
            return None

        attacker = await self.users.get_by_id_for_update(session, attack.attacker_id)
        target = await self.users.get_by_id_for_update(session, attack.target_id)
        if attacker is None or target is None or not attacker.is_active:
            attack.status = AttackStatus.RESOLVED
            attack.resolved_at = datetime.now(UTC)
            attack.result_damage = 0
            attack.loot_coin = attack.loot_diamond = attack.loot_banana = 0
            attack.is_successful = False
            return None

        teacher = await self.teachers.get_owned_for_update(
            session, attacker.id, attack.teacher_id
        ) if attack.teacher_id is not None else None
        castle_damage, injury = self.config.attack_rules.resolve(
            attack.teacher_damage_snapshot,
            attack.target_defense_power_snapshot,
            teacher.current_hp if teacher is not None else 0,
        )
        castle_result = await self.castle_service.receive_attack_damage(
            session, target.id, castle_damage
        )
        loot = self._loot(target, castle_result.applied_damage, attack.target_castle_strength_snapshot)
        loot["loot_banana"] = 0
        self._transfer_loot(session, attacker, target, loot)
        if teacher is not None and injury:
            teacher.current_hp = max(0, teacher.current_hp - injury)
            if teacher.current_hp == 0:
                teacher.status = TeacherStatus.DISABLED

        now = datetime.now(UTC)
        attack.status = AttackStatus.RESOLVED
        attack.resolved_at = now
        attack.result_damage = castle_result.applied_damage
        attack.loot_coin = loot["loot_coin"]
        attack.loot_diamond = loot["loot_diamond"]
        attack.loot_banana = 0
        attack.is_successful = castle_result.applied_damage > 0
        xp_awarded = await self._claim_attack_xp(
            session,
            attack_command_id=attack.attack_command_id,
            attack_id=attack.id,
        )
        if xp_awarded:
            attack.loot_banana = self.config.attack_rules.banana_reward
            self._transfer_loot(
                session, attacker, target,
                {"loot_coin": 0, "loot_diamond": 0,
                 "loot_banana": attack.loot_banana},
            )
        await session.flush()
        command_records = await session.scalars(
            select(Attack)
            .where(
                Attack.attack_command_id == attack.attack_command_id,
            )
            .options(
                selectinload(Attack.teacher).selectinload(UserTeacher.teacher)
            )
            .order_by(Attack.id)
        ) if attack.attack_command_id is not None else [attack]
        teacher_names = [
            item.teacher.teacher.name
            for item in command_records
            if item.teacher is not None
        ]
        return AttackResult(
            attack=attack,
            attacker_telegram_id=attacker.telegram_user_id,
            attacker_name=attacker.first_name,
            target_name=target.first_name,
            target_telegram_id=target.telegram_user_id,
            teacher_name="، ".join(teacher_names)
            or (teacher.teacher.name if teacher is not None else "دبیر"),
            ability_text=teacher.teacher.ability_text if teacher is not None else None,
            castle_damage=castle_result.applied_damage,
            teacher_injury=injury,
            castle_strength_after=castle_result.castle_strength_after,
            loot_coin=attack.loot_coin,
            loot_diamond=attack.loot_diamond,
            loot_banana=attack.loot_banana,
        )

    async def _preview(
        self, session, attacker, target, teacher_name: str | list[str]
    ) -> AttackPreview:
        names = await self._normalize_teacher_names(session, attacker.id, teacher_name)
        names = [name.strip() for name in names if name.strip()]
        if not names:
            raise TeacherNotOwned
        teachers = []
        for name in names:
            teacher = await self.teachers.get_owned_by_name_for_update(
                session, attacker.id, name
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
            teachers.append(teacher)
        castle = await self.castle_service.battle_snapshot(session, target.id)
        resolved = [
            self.config.attack_rules.resolve(
                self.teacher_service.damage(teacher),
                castle.defense_power,
                teacher.current_hp,
            )
            for teacher in teachers
        ]
        raw_damages = [item[0] for item in resolved]
        # Preview the same equipped-shield mitigation that the real attack
        # will consume; otherwise the shown loot is larger than the result.
        equipped = next(
            (
                item
                for item in await self.castle_service.shield_service.list_owned(
                    session, target.id
                )
                if item.is_equipped and item.quantity > 0
            ),
            None,
        )
        if equipped is not None:
            raw_damages = [
                self.config.apply_shield(
                    value,
                    reduction_percent=equipped.shield.reduction_percent,
                    flat_absorption=equipped.shield.flat_absorption,
                ).remaining_damage
                if index < equipped.quantity
                else value
                for index, value in enumerate(raw_damages)
            ]
        damage = min(castle.strength, sum(raw_damages))
        injury = sum(item[1] for item in resolved)
        loot = self._loot(target, damage, castle.strength)
        return AttackPreview(
            # The confirmation callback is clicked by Telegram and therefore
            # must carry the Telegram id, not the database user id.
            attacker_id=attacker.telegram_user_id,
            target_id=target.id,
            teacher_id=teachers[0].id,
            attacker_name=attacker.first_name, target_name=target.first_name,
            teacher_name="، ".join(teacher.teacher.name for teacher in teachers),
            ability_text="، ".join(
                teacher.teacher.ability_text
                for teacher in teachers
                if teacher.teacher.ability_text
            ) or None,
            teacher_damage=sum(self.teacher_service.damage(teacher) for teacher in teachers),
            defense_power=castle.defense_power, estimated_castle_damage=damage,
            estimated_teacher_injury=injury, teacher_ids=",".join(
                str(teacher.id) for teacher in teachers
            ), **loot,
        )

    async def _normalize_teacher_names(
        self, session, user_id: int, value: str | list[str]
    ) -> list[str]:
        if isinstance(value, list):
            return value
        text = value.strip()
        if not text:
            return []
        for separator in ("،", ",", "+", "|"):
            text = text.replace(separator, ",")
        text = text.replace(" و ", ",")
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]

        # If names contain spaces, greedily match the longest owned name. This
        # also allows the compact form: /attack user teacher1 teacher2.
        owned = await self.teacher_service.owned(session, user_id)
        normalized = {
            item.teacher.name.casefold(): item.teacher.name for item in owned
        }
        if text.casefold() in normalized:
            return [normalized[text.casefold()]]
        words = text.split()
        result: list[str] = []
        index = 0
        candidates = sorted(normalized, key=lambda item: len(item.split()), reverse=True)
        while index < len(words):
            match = next(
                (
                    candidate
                    for candidate in candidates
                    if " ".join(words[index : index + len(candidate.split())]).casefold()
                    == candidate
                ),
                None,
            )
            if match is None:
                result.append(words[index])
                index += 1
            else:
                result.append(normalized[match])
                index += len(match.split())
        return result

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
        return await self._attack_with_teachers(session, attacker, target, [teacher])

    async def _attack_with_teachers(
        self, session, attacker, target, teachers
    ) -> AttackResult:
        if not teachers:
            raise TeacherNotOwned
        for teacher in teachers:
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
        target_castle = await self.castle_service.battle_snapshot(session, target.id)
        total_damage = 0
        total_injury = 0
        teacher_results = []
        attack_command_id = str(uuid4())
        for teacher in teachers:
            teacher_damage = self.teacher_service.damage(teacher)
            damage, injury = self.config.attack_rules.resolve(
                teacher_damage, target_castle.defense_power, teacher.current_hp
            )
            castle_damage_result = await self.castle_service.receive_attack_damage(
                session, target.id, damage
            )
            applied_damage = castle_damage_result.applied_damage
            if injury:
                teacher.current_hp = max(0, teacher.current_hp - injury)
                if teacher.current_hp == 0:
                    teacher.status = TeacherStatus.DISABLED
            loot = self._loot(target, applied_damage, target_castle.strength)
            # XP is awarded once per attack command, not once per selected
            # teacher. Resource loot remains per actual castle damage.
            loot["loot_banana"] = 0
            self._transfer_loot(session, attacker, target, loot)
            now = datetime.now(UTC)
            attack = Attack(
                attacker_id=attacker.id,
                target_id=target.id,
                teacher_id=teacher.id,
                status=AttackStatus.RESOLVED,
                resolve_at=now,
                resolved_at=now,
                attack_command_id=attack_command_id,
                teacher_damage_snapshot=teacher_damage,
                target_castle_strength_snapshot=target_castle.strength,
                target_defense_power_snapshot=target_castle.defense_power,
                result_damage=applied_damage,
                loot_coin=loot["loot_coin"],
                loot_diamond=loot["loot_diamond"],
                loot_banana=loot["loot_banana"],
                is_successful=applied_damage > 0,
            )
            session.add(attack)
            teacher_results.append((attack, applied_damage, injury, loot, castle_damage_result))
            total_damage += applied_damage
            total_injury += injury
        await session.flush()
        last_attack, _, _, _, last_castle = teacher_results[-1]
        total_loot = {
            key: sum(item[3][key] for item in teacher_results)
            for key in ("loot_coin", "loot_diamond", "loot_banana")
        }
        xp_awarded = await self._claim_attack_xp(
            session,
            attack_command_id=attack_command_id,
            attack_id=last_attack.id,
        )
        total_loot["loot_banana"] = (
            self.config.attack_rules.banana_reward if xp_awarded else 0
        )
        if xp_awarded:
            self._transfer_loot(
                session,
                attacker,
                target,
                {"loot_coin": 0, "loot_diamond": 0,
                 "loot_banana": total_loot["loot_banana"]},
            )
        return AttackResult(
            attack=last_attack,
            attacker_telegram_id=attacker.telegram_user_id,
            attacker_name=attacker.first_name,
            target_name=target.first_name,
            target_telegram_id=target.telegram_user_id,
            teacher_name="، ".join(teacher.teacher.name for teacher in teachers),
            ability_text="، ".join(
                teacher.teacher.ability_text
                for teacher in teachers
                if teacher.teacher.ability_text
            ) or None,
            castle_damage=total_damage,
            teacher_injury=total_injury,
            castle_strength_after=last_castle.castle_strength_after,
            **total_loot,
        )

    def _loot(self, target, castle_damage: int, castle_strength: int) -> dict[str, int]:
        if castle_damage <= 0 or target.resources is None:
            return {
                "loot_coin": 0,
                "loot_diamond": 0,
                "loot_banana": self.config.attack_rules.banana_reward
                if castle_damage > 0
                else 0,
            }
        damage_factor = min(1.0, castle_damage / max(1, castle_strength))
        # Loot follows the actual fraction of the castle destroyed and the
        # configured loot percentage. A successful attack against a resource
        # balance always transfers at least one unit, avoiding a misleading
        # zero preview caused by integer truncation.
        loot_percent = self.config.loot_percent_for_castle(
            self.config.attack_rules.loot_percent,
            castle_strength,
            castle_damage,
        )
        percent = damage_factor * loot_percent / 100

        def amount(balance: int) -> int:
            if balance <= 0 or percent <= 0:
                return 0
            return min(balance, max(1, int(balance * percent)))

        return {
            "loot_coin": amount(target.resources.coin),
            "loot_diamond": amount(target.resources.diamond),
            "loot_banana": self.config.attack_rules.banana_reward,
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
            if resource_type is ResourceType.BANANA:
                # Banana is attack XP: it is minted for the attacker and is
                # never taken from the target or the attacker.
                setattr(attacker.resources, field, attacker_before + amount)
                session.add(Transaction(
                    user_id=attacker.id, resource_type=resource_type, amount=amount,
                    balance_before=attacker_before, balance_after=attacker_before + amount,
                    reason="ATTACK_XP", reference_type="ATTACK",
                ))
                continue
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
