from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AttackStatus, ResourceType, TeacherStatus
from app.core.game_logic import GameConfig, game_config
from app.models.attack import Attack
from app.models.mine import Mine
from app.models.random_attack_selection import RandomAttackSelection
from app.models.transaction import Transaction
from app.models.user_teacher import UserTeacher
from app.repositories.castle import CastleRepository
from app.repositories.teacher import TeacherRepository
from app.repositories.user import UserRepository
from app.services.castle_service import CastleService
from app.services.daily_quest_service import DailyQuestService
from app.services.lock_order import lock_attack_dependencies, lock_users_ordered
from app.services.mine_service import MineService
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    AttackerNotRegistered,
    AttackInProgress,
    AttackTargetNotRegistered,
    CannotAttackSelf,
    CastleNotFound,
    InvalidTeacherState,
    RandomAttackSelectionExpired,
    RandomOpponentNotFound,
    TargetProtectedByShield,
    TeacherInHospital,
    TeacherLimitReached,
    TeacherNotOwned,
)
from app.services.teacher_service import TeacherService


@dataclass(frozen=True)
class TeacherInjury:
    name: str
    emoji: str | None
    damage: int
    remaining_hp: int
    lost: bool


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
    blocked_by_shield: bool = False
    teacher_details: tuple[tuple[str, str | None, str | None], ...] = ()
    teacher_injuries: tuple[TeacherInjury, ...] = ()
    castle_strength_before: int = 0
    source_chat_id: int | None = None
    bot_bonus_coin: int = 0
    raid_damage: int = 0
    mine_loot_coin: int = 0
    mine_loot_diamond: int = 0


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
    teacher_emojis: tuple[str | None, ...] = ()
    teacher_details: tuple[tuple[str, str | None, str | None], ...] = ()
    bot_bonus_coin: int = 0
    estimated_raid_damage: int = 0
    mine_loot_coin: int = 0
    mine_loot_diamond: int = 0


@dataclass(frozen=True)
class AttackLaunch:
    attack_ids: tuple[int, ...]
    attack_command_id: str
    target_name: str
    teacher_name: str
    teacher_stickers: tuple[str, ...]
    resolve_at: datetime
    teacher_details: tuple[tuple[str, str | None, str | None], ...] = ()


@dataclass(frozen=True)
class RandomAttackPreview:
    preview: AttackPreview
    version: int
    expires_at: datetime
    reroll_count: int
    reroll_coin_cost: int


@dataclass(frozen=True)
class AttackTargetPreview:
    id: int
    telegram_user_id: int
    first_name: str
    username: str | None


class AttackService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config
        self.users = UserRepository()
        self.teachers = TeacherRepository()
        self.castles = CastleRepository()
        self.teacher_service = TeacherService(self.teachers, config=self.config)
        self.castle_service = CastleService(self.castles, config=self.config)
        self.mine_service = MineService(config=self.config)

    @staticmethod
    async def _ensure_no_active_attack(session: AsyncSession, attacker_id: int) -> None:
        active = await session.scalar(
            select(Attack).where(
                Attack.attacker_id == attacker_id,
                (
                    Attack.status.in_((AttackStatus.PENDING, AttackStatus.PROCESSING))
                    | (
                        (Attack.status == AttackStatus.FAILED)
                        & Attack.next_retry_at.is_not(None)
                    )
                ),
            )
        )
        if active is not None:
            raise AttackInProgress

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
            first_attack = (
                select(func.min(Attack.id))
                .where(
                    Attack.attack_command_id == attack_command_id,
                )
                .scalar_subquery()
            )
            statement = (
                update(Attack)
                .where(
                    Attack.id == first_attack,
                    Attack.attack_xp_awarded.is_(False),
                )
                .values(attack_xp_awarded=True)
            )
        result = await session.execute(statement)
        return getattr(result, "rowcount", 0) == 1

    async def attack_by_username(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_username: str,
        teacher_name: str,
    ) -> AttackResult:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        target = await self.users.get_active_by_username(session, target_username)
        if target is None:
            raise AttackTargetNotRegistered
        attacker, target = await lock_users_ordered(
            session, (attacker, target), repository=self.users
        )
        await lock_attack_dependencies(session, (attacker, target))
        await self._ensure_no_active_attack(session, attacker.id)
        return await self._attack(session, attacker, target, teacher_name)

    async def preview_by_username(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_username: str,
        teacher_name: str | list[str],
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        target = await self.users.get_active_by_username(session, target_username)
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if target is None:
            raise AttackTargetNotRegistered
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
            session, attacker_telegram_id
        )
        target = await self.users.get_by_telegram_user_id(session, target_telegram_id)
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if target is None or not target.is_active:
            raise AttackTargetNotRegistered
        if attacker.id == target.id:
            raise CannotAttackSelf
        attacker, target = await lock_users_ordered(
            session, (attacker, target), repository=self.users
        )
        await lock_attack_dependencies(session, (attacker, target))
        await self._ensure_no_active_attack(session, attacker.id)
        return await self._attack(session, attacker, target, teacher_name)

    async def preview_by_telegram_id(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_telegram_id: int,
        teacher_name: str | list[str],
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        target = await self.users.get_by_telegram_user_id(session, target_telegram_id)
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if target is None or not target.is_active:
            raise AttackTargetNotRegistered
        return await self._preview(session, attacker, target, teacher_name)

    async def available_attack_teachers(
        self, session: AsyncSession, *, attacker_telegram_id: int
    ) -> list[UserTeacher]:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        owned = await self.teacher_service.owned(session, attacker.id)
        return [
            teacher
            for teacher in owned
            if teacher.current_hp > 0
            and teacher.status in {TeacherStatus.ACTIVE, TeacherStatus.INJURED}
        ]

    async def target_preview(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        identifier: str,
    ) -> AttackTargetPreview:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        normalized = identifier.strip()
        if normalized.isdecimal():
            target = await self.users.get_by_telegram_user_id(session, int(normalized))
            if target is not None and not target.is_active:
                target = None
        else:
            target = await self.users.get_active_by_username(session, normalized)
        if target is None:
            raise AttackTargetNotRegistered
        if target.id == attacker.id:
            raise CannotAttackSelf
        await self._ensure_target_attackable(session, target.id)
        return AttackTargetPreview(
            id=target.id,
            telegram_user_id=target.telegram_user_id,
            first_name=target.first_name,
            username=target.username,
        )

    async def preview_by_teacher_ids(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_id: int,
        teacher_ids: list[int],
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        target = await self.users.get_active_by_id(session, target_id)
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if target is None:
            raise AttackTargetNotRegistered
        unique_ids = list(dict.fromkeys(teacher_ids))
        if not unique_ids:
            raise TeacherNotOwned
        if len(unique_ids) > self.config.max_attack_teachers:
            raise TeacherLimitReached
        return await self._preview_by_teacher_ids(
            session, attacker, target, ",".join(map(str, unique_ids))
        )

    async def prepare_random_preview_by_teacher_ids(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        teacher_ids: list[int],
    ) -> RandomAttackPreview:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        unique_ids = list(dict.fromkeys(teacher_ids))
        if not unique_ids:
            raise TeacherNotOwned
        if len(unique_ids) > self.config.max_attack_teachers:
            raise TeacherLimitReached
        teachers = await self.available_attack_teachers(
            session, attacker_telegram_id=attacker_telegram_id
        )
        names_by_id = {teacher.id: teacher.teacher.name for teacher in teachers}
        try:
            names = [names_by_id[teacher_id] for teacher_id in unique_ids]
        except KeyError as exc:
            raise TeacherNotOwned from exc
        return await self.prepare_random_preview(
            session,
            attacker_telegram_id=attacker_telegram_id,
            teacher_name=names,
        )

    async def preview_random(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        teacher_name: str | list[str],
    ) -> AttackPreview:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered

        _, preview = await self._find_random_preview(
            session, attacker, teacher_name=teacher_name
        )
        return preview

    async def prepare_random_preview(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        teacher_name: str | list[str],
    ) -> RandomAttackPreview:
        """Get a durable free random opponent, preserving a live choice."""
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        # Random-selection locks always precede the user row. Confirm and
        # reroll follow this order too, avoiding a cross-path deadlock.
        selection = await self._selection_for_update(session, attacker.id)
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if selection is None:
            # Two first-time commands can both observe no row before one gets
            # the user lock. Re-read after that lock to preserve one selection.
            selection = await self._selection_for_update(session, attacker.id)
        await self._ensure_no_active_attack(session, attacker.id)
        now = datetime.now(UTC)
        recent_ids = self._selection_recent_ids(selection)
        selection_is_live = selection is not None and selection.expires_at > now
        target = (
            await self.users.get_active_by_id(session, selection.target_id)
            if selection_is_live
            else None
        )
        if selection is not None and target is not None:
            try:
                # Keep a valid choice stable; replace it without a fee if it
                # became protected or lost its castle after selection.
                preview = await self._preview(session, attacker, target, teacher_name)
            except (TargetProtectedByShield, AttackTargetNotRegistered, CastleNotFound):
                pass
            else:
                if selection.teacher_ids != preview.teacher_ids:
                    selection.teacher_ids = preview.teacher_ids
                    selection.version += 1
                    await session.flush()
                return self._random_preview(selection, preview)

        target, preview = await self._find_random_preview(
            session,
            attacker,
            teacher_name=teacher_name,
            recent_target_ids=recent_ids,
            exclude_target_ids={selection.target_id} if selection_is_live else set(),
        )
        expires_at = now + timedelta(
            seconds=self.config.attack_rules.random_selection_ttl_seconds
        )
        if selection is None:
            selection = RandomAttackSelection(
                attacker_id=attacker.id,
                target_id=target.id,
                teacher_ids=preview.teacher_ids,
                recent_target_ids=self._remember_random_target(recent_ids, target.id),
                expires_at=expires_at,
            )
            session.add(selection)
        else:
            selection.target_id = target.id
            selection.teacher_ids = preview.teacher_ids
            selection.recent_target_ids = self._remember_random_target(
                recent_ids, target.id
            )
            selection.version += 1
            if not selection_is_live:
                selection.reroll_count = 0
            selection.expires_at = expires_at
        await session.flush()
        return self._random_preview(selection, preview)

    async def reroll_random_preview(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        version: int,
    ) -> RandomAttackPreview:
        """Spend coins atomically to replace one still-valid random opponent."""
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        selection = await self._selection_for_update(session, attacker.id)
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id, for_update=True
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        await self._ensure_no_active_attack(session, attacker.id)
        now = datetime.now(UTC)
        if (
            selection is None
            or selection.expires_at <= now
            or selection.version != version
        ):
            raise RandomAttackSelectionExpired
        current_target = await self.users.get_active_by_id(session, selection.target_id)
        current_attackable = current_target is not None
        if current_target is not None:
            try:
                await self._preview_by_teacher_ids(
                    session, attacker, current_target, selection.teacher_ids
                )
            except (TargetProtectedByShield, AttackTargetNotRegistered, CastleNotFound):
                current_attackable = False
        recent_ids = self._selection_recent_ids(selection)
        target, preview = await self._find_random_preview(
            session,
            attacker,
            teacher_ids=selection.teacher_ids,
            recent_target_ids=recent_ids,
            exclude_target_ids={selection.target_id},
        )
        if current_attackable:
            await ResourceService.debit_coin(
                session,
                attacker.resources,
                user_id=attacker.id,
                amount=self.config.attack_rules.random_reroll_coin_cost,
                reason="RANDOM_ATTACK_REROLL",
                reference_type="RANDOM_ATTACK_SELECTION",
                reference_id=attacker.id,
            )
        selection.target_id = target.id
        selection.recent_target_ids = self._remember_random_target(
            recent_ids, target.id
        )
        selection.version += 1
        if current_attackable:
            selection.reroll_count += 1
        selection.expires_at = now + timedelta(
            seconds=self.config.attack_rules.random_selection_ttl_seconds
        )
        await session.flush()
        return self._random_preview(selection, preview)

    async def launch_random_attack(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        version: int,
        source_chat_id: int | None = None,
    ) -> AttackLaunch:
        """Launch exactly the target and teachers retained in the selection."""
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        selection = await self._selection_for_update(session, attacker.id)
        if (
            selection is None
            or selection.expires_at <= datetime.now(UTC)
            or selection.version != version
        ):
            raise RandomAttackSelectionExpired
        teacher_ids = self._parse_teacher_ids(selection.teacher_ids)
        launch = await self.start_attack_by_ids(
            session,
            attacker_telegram_id=attacker_telegram_id,
            target_id=selection.target_id,
            teacher_ids=teacher_ids,
            source_chat_id=source_chat_id,
        )
        # Retain the short opponent history for the next random attack. The
        # expired selection still rejects every stale confirmation button.
        selection.expires_at = datetime.now(UTC)
        selection.version += 1
        return launch

    async def attack_by_ids(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_id: int,
        teacher_id: int,
        teacher_ids: list[int] | None = None,
    ) -> AttackResult:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        target = await self.users.get_active_by_id(session, target_id)
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if target is None or not target.is_active:
            raise AttackTargetNotRegistered
        attacker, target = await lock_users_ordered(
            session, (attacker, target), repository=self.users
        )
        await lock_attack_dependencies(session, (attacker, target))
        await self._ensure_no_active_attack(session, attacker.id)
        await self._ensure_target_attackable(session, target.id)
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
        await self._ensure_target_attackable(
            session, target.id, tuple(item.teacher.name for item in teachers)
        )
        return await self._attack_with_teachers(session, attacker, target, teachers)

    async def start_attack_by_ids(
        self,
        session: AsyncSession,
        *,
        attacker_telegram_id: int,
        target_id: int,
        teacher_ids: list[int],
        duration: timedelta = timedelta(minutes=2),
        source_chat_id: int | None = None,
    ) -> AttackLaunch:
        attacker = await self.users.get_by_telegram_user_id(
            session, attacker_telegram_id
        )
        target = await self.users.get_active_by_id(session, target_id)
        if attacker is None or not attacker.is_active:
            raise AttackerNotRegistered
        if target is None or not target.is_active:
            raise AttackTargetNotRegistered
        if attacker.id == target.id:
            raise CannotAttackSelf
        attacker, target = await lock_users_ordered(
            session, (attacker, target), repository=self.users
        )
        await lock_attack_dependencies(session, (attacker, target))
        await self._ensure_no_active_attack(session, attacker.id)
        await self._ensure_target_attackable(session, target.id)

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
            if teacher.current_hp <= 0:
                await session.delete(teacher)
                raise InvalidTeacherState
            if teacher.status is TeacherStatus.RECOVERING:
                raise TeacherInHospital
            if teacher.status not in {TeacherStatus.ACTIVE, TeacherStatus.INJURED}:
                raise InvalidTeacherState
            teachers.append(teacher)

        await self._ensure_target_attackable(
            session, target.id, tuple(item.teacher.name for item in teachers)
        )
        castle = await self.castle_service.battle_snapshot(session, target.id)
        await self.castle_service.shield_service.apply_outgoing_attack_time_penalty(
            session, attacker.id, duration
        )
        resolve_at = datetime.now(UTC) + duration
        attack_command_id = str(uuid4())
        created_attacks: list[Attack] = []
        for teacher in teachers:
            attack = Attack(
                attacker_id=attacker.id,
                target_id=target.id,
                teacher_id=teacher.id,
                status=AttackStatus.PENDING,
                resolve_at=resolve_at,
                attack_command_id=attack_command_id,
                source_chat_id=source_chat_id,
                teacher_name_snapshot=teacher.teacher.name,
                teacher_emoji_snapshot=teacher.teacher.emoji,
                teacher_ability_snapshot=teacher.teacher.ability_text,
                teacher_damage_snapshot=self.teacher_service.damage(teacher),
                target_castle_strength_snapshot=castle.strength,
                target_defense_power_snapshot=castle.defense_power,
            )
            session.add(attack)
            created_attacks.append(attack)
        await session.flush()
        return AttackLaunch(
            attack_ids=tuple(attack.id for attack in created_attacks),
            attack_command_id=attack_command_id,
            target_name=target.first_name,
            teacher_name="، ".join(teacher.teacher.name for teacher in teachers),
            teacher_stickers=tuple(
                teacher.teacher.sticker
                for teacher in teachers
                if teacher.teacher.sticker
            ),
            resolve_at=resolve_at,
            teacher_details=tuple(
                (
                    teacher.teacher.name,
                    teacher.teacher.ability_text,
                    teacher.teacher.emoji,
                )
                for teacher in teachers
            ),
        )

    async def resolve_pending_attack(
        self, session: AsyncSession, attack_id: int
    ) -> AttackResult | None:
        attack = await session.scalar(
            select(Attack)
            .where(
                Attack.id == attack_id,
                Attack.status.in_(
                    (
                        AttackStatus.PENDING,
                        AttackStatus.PROCESSING,
                        AttackStatus.FAILED,
                    )
                ),
            )
            .with_for_update()
        )
        if attack is None:
            return None
        if attack.status is AttackStatus.PENDING:
            attack.status = AttackStatus.PROCESSING
            attack.processing_at = datetime.now(UTC)
            await session.flush()

        users = {}
        for user_id in sorted((attack.attacker_id, attack.target_id)):
            users[user_id] = await self.users.get_by_id_for_update(session, user_id)
        attacker = users[attack.attacker_id]
        target = users[attack.target_id]
        if (
            attacker is None
            or target is None
            or not attacker.is_active
            or not target.is_active
        ):
            attack.status = AttackStatus.RESOLVED
            attack.resolved_at = datetime.now(UTC)
            attack.result_damage = 0
            attack.loot_coin = attack.loot_diamond = attack.loot_banana = 0
            attack.is_successful = False
            return None
        if attacker.id == target.id:
            # Reject legacy/tampered pending rows without ever touching the
            # shared resource object. Treating one wallet as both sides of a
            # loot transfer would mint resources.
            attack.status = AttackStatus.RESOLVED
            attack.resolved_at = datetime.now(UTC)
            attack.result_damage = 0
            attack.loot_coin = attack.loot_diamond = attack.loot_banana = 0
            attack.is_successful = False
            return None
        _, castles = await lock_attack_dependencies(session, (attacker, target))
        target_castle = castles.get(target.id)
        if target_castle is None:
            raise AttackTargetNotRegistered
        teacher = (
            await self.teachers.get_owned_for_update(
                session, attacker.id, attack.teacher_id
            )
            if attack.teacher_id is not None
            else None
        )
        teacher_name = attack.teacher_name_snapshot or (
            teacher.teacher.name if teacher is not None else "دبیر"
        )
        teacher_ability = attack.teacher_ability_snapshot or (
            teacher.teacher.ability_text if teacher is not None else None
        )
        teacher_icon = attack.teacher_emoji_snapshot or (
            teacher.teacher.emoji if teacher is not None else None
        )
        command_names: tuple[str, ...] = (teacher_name,)
        if attack.attack_command_id is not None:
            names = await session.scalars(
                select(Attack.teacher_name_snapshot).where(
                    Attack.attack_command_id == attack.attack_command_id
                )
            )
            command_names = tuple(name for name in names if name) or command_names
        if await self.castle_service.shield_service.has_free_shield(
            session, target.id
        ) or (
            target_castle.strength > 0
            and await self.castle_service.shield_service.has_active_shield(
                session, target.id, command_names
            )
        ):
            now = datetime.now(UTC)
            attack.status = AttackStatus.RESOLVED
            attack.resolved_at = now
            attack.result_damage = 0
            attack.loot_coin = attack.loot_diamond = attack.loot_banana = 0
            attack.is_successful = False
            attack.result_teacher_injury = 0
            await session.flush()
            return AttackResult(
                attack=attack,
                attacker_telegram_id=attacker.telegram_user_id,
                attacker_name=attacker.first_name,
                target_name=target.first_name,
                target_telegram_id=target.telegram_user_id,
                teacher_name=teacher_name,
                ability_text=teacher_ability,
                castle_damage=0,
                teacher_injury=0,
                castle_strength_after=target_castle.strength,
                loot_coin=0,
                loot_diamond=0,
                loot_banana=0,
                blocked_by_shield=True,
                teacher_details=((teacher_name, teacher_ability, teacher_icon),),
                castle_strength_before=attack.target_castle_strength_snapshot,
                source_chat_id=attack.source_chat_id,
            )
        castle_damage, injury = self.config.attack_rules.resolve(
            attack.teacher_damage_snapshot,
            (
                target_castle.defense.defense_power
                if attack.target_castle_strength_snapshot == 0
                and target_castle.strength > 0
                and target_castle.defense is not None
                else attack.target_defense_power_snapshot
            )
            if target_castle.strength > 0
            else 0,
            teacher.current_hp if teacher is not None else 0,
        )
        castle_result = await self.castle_service.receive_attack_damage(
            session, target.id, castle_damage, teacher_names=command_names
        )
        raid_damage = max(
            0,
            castle_result.incoming_damage
            - castle_result.blocked_damage
            - castle_result.applied_damage,
        )
        loot_damage = castle_result.applied_damage or raid_damage
        loot = self._loot(
            target,
            loot_damage,
            castle_result.castle_strength_before,
            attack.teacher_damage_snapshot,
        )
        mine_loot = await self._raid_mine(
            session,
            target,
            loot_damage=loot_damage,
            castle_strength=castle_result.castle_strength_before,
            attack_power=attack.teacher_damage_snapshot,
            breached=castle_result.castle_strength_after == 0
            and loot["loot_coin"] == 0
            and loot["loot_diamond"] == 0,
        )
        empty_target_bonus = (
            self._empty_target_bonus(target, loot_damage)
            if not any((loot["loot_coin"], loot["loot_diamond"], *mine_loot))
            else 0
        )
        loot["loot_banana"] = 0
        self._transfer_loot(session, attacker, target, loot, attack_id=attack.id)
        self._credit_mine_loot(session, attacker, mine_loot, attack_id=attack.id)
        if teacher is not None and injury:
            # Legacy in-flight attacks can resolve after hospital admission.
            # Their injury interrupts that treatment; never leave an open
            # recovery attached to a teacher that is INJURED again.
            if teacher.status is TeacherStatus.RECOVERING:
                interrupted_at = datetime.now(UTC)
                for recovery in teacher.recoveries:
                    if recovery.completed_at is None:
                        recovery.completed_at = interrupted_at
            teacher.current_hp = max(0, teacher.current_hp - injury)
            if teacher.current_hp == 0:
                await session.delete(teacher)
            else:
                teacher.status = TeacherStatus.INJURED

        now = datetime.now(UTC)
        attack.status = AttackStatus.RESOLVED
        attack.resolved_at = now
        attack.result_damage = castle_result.applied_damage
        attack.result_raid_damage = raid_damage
        attack.result_teacher_injury = injury
        attack.loot_coin = loot["loot_coin"] + mine_loot[0]
        attack.loot_diamond = loot["loot_diamond"] + mine_loot[1]
        attack.mine_loot_coin = mine_loot[0]
        attack.mine_loot_diamond = mine_loot[1]
        attack.loot_banana = 0
        attack.is_successful = loot_damage > 0
        quest_service = DailyQuestService()
        await quest_service.record_event(
            session,
            user_id=attacker.id,
            event_type="COMPLETE_BATTLES",
            event_id=(
                f"attack-command:{attack.attack_command_id}"
                if attack.attack_command_id is not None
                else f"attack:{attack.id}"
            ),
        )
        xp_awarded = (
            await self._claim_attack_xp(
                session,
                attack_command_id=attack.attack_command_id,
                attack_id=attack.id,
            )
            if loot_damage > 0
            else False
        )
        if xp_awarded:
            attack.loot_banana = self.config.attack_rules.banana_reward
            self._transfer_loot(
                session,
                attacker,
                target,
                {"loot_coin": 0, "loot_diamond": 0, "loot_banana": attack.loot_banana},
                attack_id=attack.id,
            )
            if empty_target_bonus:
                awarded_bonus = self._award_empty_target_bonus(
                    session, attacker, empty_target_bonus, attack_id=attack.id
                )
                attack.bot_bonus_coin = awarded_bonus
                attack.loot_coin = (attack.loot_coin or 0) + awarded_bonus
        await session.flush()
        command_records = (
            await session.scalars(
                select(Attack)
                .where(
                    Attack.attack_command_id == attack.attack_command_id,
                )
                .options(selectinload(Attack.teacher).selectinload(UserTeacher.teacher))
                .order_by(Attack.id)
            )
            if attack.attack_command_id is not None
            else [attack]
        )
        teacher_names = [
            item.teacher.teacher.name
            for item in command_records
            if item.teacher is not None
        ]
        if teacher is not None and teacher_name not in teacher_names:
            teacher_names.insert(0, teacher_name)
        return AttackResult(
            attack=attack,
            attacker_telegram_id=attacker.telegram_user_id,
            attacker_name=attacker.first_name,
            target_name=target.first_name,
            target_telegram_id=target.telegram_user_id,
            teacher_name="، ".join(teacher_names) or teacher_name,
            ability_text=teacher_ability,
            castle_damage=castle_result.applied_damage,
            teacher_injury=injury,
            castle_strength_after=castle_result.castle_strength_after,
            loot_coin=attack.loot_coin,
            loot_diamond=attack.loot_diamond,
            loot_banana=attack.loot_banana,
            teacher_details=((teacher_name, teacher_ability, teacher_icon),),
            castle_strength_before=castle_result.castle_strength_before,
            source_chat_id=attack.source_chat_id,
            bot_bonus_coin=attack.bot_bonus_coin,
            raid_damage=raid_damage,
            mine_loot_coin=mine_loot[0],
            mine_loot_diamond=mine_loot[1],
        )

    async def _selection_for_update(
        self, session: AsyncSession, attacker_id: int
    ) -> RandomAttackSelection | None:
        return await session.scalar(
            select(RandomAttackSelection)
            .where(RandomAttackSelection.attacker_id == attacker_id)
            .with_for_update()
        )

    async def _pick_random_target(
        self,
        session: AsyncSession,
        attacker,
        *,
        exclude_target_ids: set[int] | None = None,
        recent_target_ids: tuple[int, ...] = (),
    ):
        levels = await self.users.list_active_levels_by_proximity(
            session, level=attacker.level, exclude_user_id=attacker.id
        )
        hard_excluded = exclude_target_ids or set()
        nearby = [level for level in levels if abs(level - attacker.level) <= 2]
        distant = [level for level in levels if abs(level - attacker.level) > 2]
        # Keep matchups close in level. Within that range, prefer fresh people;
        # only widen the level gap when every nearby opponent is unavailable.
        for candidate_levels, exclusions in (
            (nearby, hard_excluded | set(recent_target_ids)),
            (nearby, hard_excluded),
            (distant, hard_excluded | set(recent_target_ids)),
            (distant, hard_excluded),
        ):
            for level in candidate_levels:
                target = await self.users.pick_random_active_at_level(
                    session,
                    level=level,
                    exclude_user_id=attacker.id,
                    exclude_target_ids=exclusions,
                )
                if target is not None:
                    return target
        raise RandomOpponentNotFound

    async def _find_random_preview(
        self,
        session: AsyncSession,
        attacker,
        *,
        teacher_name: str | list[str] | None = None,
        teacher_ids: str | None = None,
        recent_target_ids: tuple[int, ...] = (),
        exclude_target_ids: set[int] | None = None,
    ):
        excluded = set(exclude_target_ids or ())
        for _ in range(5):
            target = await self._pick_random_target(
                session,
                attacker,
                exclude_target_ids=excluded,
                recent_target_ids=recent_target_ids,
            )
            try:
                preview = (
                    await self._preview_by_teacher_ids(
                        session, attacker, target, teacher_ids
                    )
                    if teacher_ids is not None
                    else await self._preview(session, attacker, target, teacher_name)
                )
            except (TargetProtectedByShield, AttackTargetNotRegistered, CastleNotFound):
                # A shield can activate after the candidate query. Try another
                # eligible opponent before reporting that the pool is empty.
                excluded.add(target.id)
                continue
            return target, preview
        raise RandomOpponentNotFound

    @staticmethod
    def _selection_recent_ids(
        selection: RandomAttackSelection | None,
    ) -> tuple[int, ...]:
        if selection is None:
            return ()
        ids = [
            int(part)
            for part in (selection.recent_target_ids or "").split(",")
            if part.isdecimal()
        ]
        if selection.target_id not in ids:
            ids.append(selection.target_id)
        return tuple(ids[-8:])

    @staticmethod
    def _remember_random_target(recent_ids: tuple[int, ...], target_id: int) -> str:
        ids = [item for item in recent_ids if item != target_id]
        ids.append(target_id)
        return ",".join(str(item) for item in ids[-8:])

    def _random_preview(
        self, selection: RandomAttackSelection, preview: AttackPreview
    ) -> RandomAttackPreview:
        return RandomAttackPreview(
            preview=preview,
            version=selection.version,
            expires_at=selection.expires_at,
            reroll_count=selection.reroll_count,
            reroll_coin_cost=self.config.attack_rules.random_reroll_coin_cost,
        )

    @staticmethod
    def _parse_teacher_ids(value: str) -> list[int]:
        try:
            teacher_ids = [int(item) for item in value.split(",") if item.strip()]
        except ValueError as exc:
            raise TeacherNotOwned from exc
        if not teacher_ids or len(teacher_ids) != len(set(teacher_ids)):
            raise TeacherNotOwned
        return teacher_ids

    async def _preview(
        self, session, attacker, target, teacher_name: str | list[str]
    ) -> AttackPreview:
        if attacker.id == target.id:
            raise CannotAttackSelf
        names = await self._normalize_teacher_names(session, attacker.id, teacher_name)
        names = [name.strip() for name in names if name.strip()]
        if not names:
            raise TeacherNotOwned
        teachers = []
        for name in names:
            teacher = await self.teachers.get_owned_by_name(session, attacker.id, name)
            if teacher is None:
                raise TeacherNotOwned
            if teacher.current_hp <= 0:
                raise InvalidTeacherState
            if teacher.status is TeacherStatus.RECOVERING:
                raise TeacherInHospital
            if teacher.status not in {TeacherStatus.ACTIVE, TeacherStatus.INJURED}:
                raise InvalidTeacherState
            teachers.append(teacher)
        return await self._preview_with_teachers(session, attacker, target, teachers)

    async def _preview_by_teacher_ids(
        self, session, attacker, target, teacher_ids: str
    ) -> AttackPreview:
        if attacker.id == target.id:
            raise CannotAttackSelf
        teachers = []
        for teacher_id in self._parse_teacher_ids(teacher_ids):
            teacher = await self.teachers.get_owned(session, attacker.id, teacher_id)
            if teacher is None:
                raise TeacherNotOwned
            if teacher.current_hp <= 0:
                raise InvalidTeacherState
            if teacher.status is TeacherStatus.RECOVERING:
                raise TeacherInHospital
            if teacher.status not in {TeacherStatus.ACTIVE, TeacherStatus.INJURED}:
                raise InvalidTeacherState
            teachers.append(teacher)
        return await self._preview_with_teachers(session, attacker, target, teachers)

    async def _preview_with_teachers(
        self, session, attacker, target, teachers
    ) -> AttackPreview:
        names = tuple(item.teacher.name for item in teachers)
        if names:
            await self._ensure_target_attackable(session, target.id, names)
        else:
            await self._ensure_target_attackable(session, target.id)
        castle = await self.castle_service.battle_snapshot(session, target.id)
        remaining_strength = castle.strength
        raid_damage = 0
        injury = 0
        wallet_coin = target.resources.coin if target.resources is not None else 0
        wallet_diamond = target.resources.diamond if target.resources is not None else 0
        loot = {"loot_coin": 0, "loot_diamond": 0, "loot_banana": 0}
        mine_loot_coin = mine_loot_diamond = 0
        mine_cargo = None
        for teacher in teachers:
            teacher_power = self.teacher_service.damage(teacher)
            strength_before = remaining_strength
            raw_damage, teacher_injury = self.config.attack_rules.resolve(
                teacher_power,
                castle.defense_power if remaining_strength > 0 else 0,
                teacher.current_hp,
            )
            injury += teacher_injury
            unblocked_damage = (
                (
                    await self.castle_service.shield_service.mitigate_attack(
                        session, target.id, raw_damage, teacher_names=names
                    )
                ).remaining_damage
                if remaining_strength > 0
                else raw_damage
            )
            applied_damage = min(remaining_strength, unblocked_damage)
            remaining_strength -= applied_damage
            raid_damage += unblocked_damage - applied_damage
            loot_damage = applied_damage or (unblocked_damage - applied_damage)
            wallet_loot = self._loot(
                target,
                loot_damage,
                strength_before,
                teacher_power,
                coin_balance=wallet_coin,
                diamond_balance=wallet_diamond,
            )
            wallet_coin -= wallet_loot["loot_coin"]
            wallet_diamond -= wallet_loot["loot_diamond"]
            loot["loot_coin"] += wallet_loot["loot_coin"]
            loot["loot_diamond"] += wallet_loot["loot_diamond"]
            if (
                remaining_strength == 0
                and loot_damage > 0
                and wallet_loot["loot_coin"] == 0
                and wallet_loot["loot_diamond"] == 0
            ):
                if mine_cargo is None:
                    mine_cargo = await self._preview_mine_cargo(session, target.id)
                if mine_cargo is not None:
                    cargo_loot = self._loot(
                        target,
                        loot_damage,
                        strength_before,
                        teacher_power,
                        coin_balance=mine_cargo.today_coin,
                        diamond_balance=mine_cargo.today_diamond,
                    )
                    mine_cargo.today_coin -= cargo_loot["loot_coin"]
                    mine_cargo.today_diamond -= cargo_loot["loot_diamond"]
                    mine_loot_coin += cargo_loot["loot_coin"]
                    mine_loot_diamond += cargo_loot["loot_diamond"]
                    loot["loot_coin"] += cargo_loot["loot_coin"]
                    loot["loot_diamond"] += cargo_loot["loot_diamond"]
        damage = castle.strength - remaining_strength
        loot_damage = damage or raid_damage
        empty_target_bonus = (
            self._empty_target_bonus(target, loot_damage)
            if loot["loot_coin"] == 0 and loot["loot_diamond"] == 0
            else 0
        )
        loot["loot_coin"] += empty_target_bonus
        loot["loot_banana"] = (
            self.config.attack_rules.banana_reward if loot_damage > 0 else 0
        )
        return AttackPreview(
            # The confirmation callback is clicked by Telegram and therefore
            # must carry the Telegram id, not the database user id.
            attacker_id=attacker.telegram_user_id,
            target_id=target.id,
            teacher_id=teachers[0].id,
            attacker_name=attacker.first_name,
            target_name=target.first_name,
            teacher_name="، ".join(teacher.teacher.name for teacher in teachers),
            ability_text="، ".join(
                teacher.teacher.ability_text
                for teacher in teachers
                if teacher.teacher.ability_text
            )
            or None,
            teacher_damage=sum(
                self.teacher_service.damage(teacher) for teacher in teachers
            ),
            defense_power=castle.defense_power,
            estimated_castle_damage=damage,
            estimated_teacher_injury=injury,
            teacher_ids=",".join(str(teacher.id) for teacher in teachers),
            teacher_emojis=tuple(teacher.teacher.emoji for teacher in teachers),
            teacher_details=tuple(
                (
                    teacher.teacher.name,
                    teacher.teacher.ability_text,
                    teacher.teacher.emoji,
                )
                for teacher in teachers
            ),
            bot_bonus_coin=empty_target_bonus,
            estimated_raid_damage=raid_damage,
            mine_loot_coin=mine_loot_coin,
            mine_loot_diamond=mine_loot_diamond,
            **loot,
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
        normalized = {item.teacher.name.casefold(): item.teacher.name for item in owned}
        if text.casefold() in normalized:
            return [normalized[text.casefold()]]
        words = text.split()
        result: list[str] = []
        index = 0
        candidates = sorted(
            normalized, key=lambda item: len(item.split()), reverse=True
        )
        while index < len(words):
            match = next(
                (
                    candidate
                    for candidate in candidates
                    if " ".join(
                        words[index : index + len(candidate.split())]
                    ).casefold()
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

    async def _attack(
        self, session, attacker, target, teacher_name: str
    ) -> AttackResult:
        if attacker.id == target.id:
            raise CannotAttackSelf
        teacher = await self.teachers.get_owned_by_name_for_update(
            session, attacker.id, teacher_name
        )
        if teacher is None:
            raise TeacherNotOwned
        if teacher.status is TeacherStatus.RECOVERING:
            raise TeacherInHospital
        if teacher.status not in {TeacherStatus.ACTIVE, TeacherStatus.INJURED}:
            raise InvalidTeacherState

        return await self._attack_with_teacher(session, attacker, target, teacher)

    async def _attack_with_teacher(
        self, session, attacker, target, teacher
    ) -> AttackResult:
        return await self._attack_with_teachers(session, attacker, target, [teacher])

    async def _attack_with_teachers(
        self, session, attacker, target, teachers
    ) -> AttackResult:
        if attacker.id == target.id:
            raise CannotAttackSelf
        if not teachers:
            raise TeacherNotOwned
        for teacher in teachers:
            if teacher.current_hp <= 0:
                await session.delete(teacher)
                raise InvalidTeacherState
            if teacher.status is TeacherStatus.RECOVERING:
                raise TeacherInHospital
            if teacher.status not in {TeacherStatus.ACTIVE, TeacherStatus.INJURED}:
                raise InvalidTeacherState
        _, castles = await lock_attack_dependencies(session, (attacker, target))
        names = tuple(item.teacher.name for item in teachers)
        await self._ensure_target_attackable(session, target.id, names)
        target_castle = castles.get(target.id)
        if target_castle is None:
            raise AttackTargetNotRegistered
        if target_castle.defense is None:
            # Repair legacy/incomplete castle rows before deriving battle
            # snapshots, rather than crashing an attack on a nullable ORM
            # relationship.
            from app.models.defense import Defense

            target_castle.defense = Defense(
                defense_power=self.config.initial_defense_power
            )
            await session.flush()
        total_damage = 0
        total_raid_damage = 0
        total_injury = 0
        teacher_results = []
        attack_command_id = str(uuid4())
        total_mine_coin = 0
        total_mine_diamond = 0
        target_started_empty = not self._target_has_lootable_resources(target)
        for teacher in teachers:
            teacher_damage = self.teacher_service.damage(teacher)
            damage, injury = self.config.attack_rules.resolve(
                teacher_damage,
                target_castle.defense.defense_power
                if target_castle.strength > 0
                else 0,
                teacher.current_hp,
            )
            castle_damage_result = await self.castle_service.receive_attack_damage(
                session, target.id, damage, teacher_names=names
            )
            applied_damage = castle_damage_result.applied_damage
            raid_damage = max(
                0,
                castle_damage_result.incoming_damage
                - castle_damage_result.blocked_damage
                - applied_damage,
            )
            loot_damage = applied_damage or raid_damage
            if injury:
                teacher.current_hp = max(0, teacher.current_hp - injury)
                if teacher.current_hp == 0:
                    await session.delete(teacher)
                else:
                    teacher.status = TeacherStatus.INJURED
            loot = self._loot(
                target,
                loot_damage,
                castle_damage_result.castle_strength_before,
                teacher_damage,
            )
            mine_loot = await self._raid_mine(
                session,
                target,
                loot_damage=loot_damage,
                castle_strength=castle_damage_result.castle_strength_before,
                attack_power=teacher_damage,
                breached=castle_damage_result.castle_strength_after == 0
                and loot["loot_coin"] == 0
                and loot["loot_diamond"] == 0,
            )
            # XP is awarded once per attack command, not once per selected
            # teacher. Resource loot remains per actual castle damage.
            loot["loot_banana"] = 0
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
                target_castle_strength_snapshot=castle_damage_result.castle_strength_before,
                target_defense_power_snapshot=(
                    target_castle.defense.defense_power
                    if castle_damage_result.castle_strength_before > 0
                    else 0
                ),
                result_damage=applied_damage,
                result_raid_damage=raid_damage,
                loot_coin=loot["loot_coin"] + mine_loot[0],
                loot_diamond=loot["loot_diamond"] + mine_loot[1],
                loot_banana=loot["loot_banana"],
                mine_loot_coin=mine_loot[0],
                mine_loot_diamond=mine_loot[1],
                is_successful=loot_damage > 0,
            )
            session.add(attack)
            await session.flush()
            self._transfer_loot(session, attacker, target, loot, attack_id=attack.id)
            self._credit_mine_loot(session, attacker, mine_loot, attack_id=attack.id)
            teacher_results.append(
                (attack, applied_damage, injury, loot, castle_damage_result)
            )
            total_damage += applied_damage
            total_raid_damage += raid_damage
            total_mine_coin += mine_loot[0]
            total_mine_diamond += mine_loot[1]
            total_injury += injury
        await session.flush()
        last_attack, _, _, _, last_castle = teacher_results[-1]
        total_loot = {
            key: sum(item[3][key] for item in teacher_results)
            for key in ("loot_coin", "loot_diamond", "loot_banana")
        }
        total_loot["loot_coin"] += total_mine_coin
        total_loot["loot_diamond"] += total_mine_diamond
        xp_awarded = (
            await self._claim_attack_xp(
                session,
                attack_command_id=attack_command_id,
                attack_id=last_attack.id,
            )
            if total_damage + total_raid_damage > 0
            else False
        )
        total_loot["loot_banana"] = (
            self.config.attack_rules.banana_reward if xp_awarded else 0
        )
        if xp_awarded:
            self._transfer_loot(
                session,
                attacker,
                target,
                {
                    "loot_coin": 0,
                    "loot_diamond": 0,
                    "loot_banana": total_loot["loot_banana"],
                },
                attack_id=last_attack.id,
            )
            if (
                target_started_empty
                and total_loot["loot_coin"] == 0
                and total_loot["loot_diamond"] == 0
                and self.config.attack_rules.empty_target_bonus_coin
            ):
                bonus = self.config.attack_rules.empty_target_bonus_coin
                awarded_bonus = self._award_empty_target_bonus(
                    session, attacker, bonus, attack_id=last_attack.id
                )
                last_attack.bot_bonus_coin = awarded_bonus
                last_attack.loot_coin = (last_attack.loot_coin or 0) + awarded_bonus
                total_loot["loot_coin"] += awarded_bonus
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
            )
            or None,
            castle_damage=total_damage,
            teacher_injury=total_injury,
            castle_strength_after=last_castle.castle_strength_after,
            loot_coin=total_loot["loot_coin"],
            loot_diamond=total_loot["loot_diamond"],
            loot_banana=total_loot["loot_banana"],
            teacher_details=tuple(
                (
                    teacher.teacher.name,
                    teacher.teacher.ability_text,
                    teacher.teacher.emoji,
                )
                for teacher in teachers
            ),
            castle_strength_before=teacher_results[0][
                0
            ].target_castle_strength_snapshot,
            bot_bonus_coin=last_attack.bot_bonus_coin,
            raid_damage=total_raid_damage,
            mine_loot_coin=total_mine_coin,
            mine_loot_diamond=total_mine_diamond,
        )

    async def _ensure_target_attackable(
        self,
        session: AsyncSession,
        target_id: int,
        teacher_names: tuple[str, ...] | None = None,
    ) -> None:
        castle = await self.castles.get_by_user(session, target_id)
        shield_service = self.castle_service.shield_service
        if await shield_service.has_free_shield(session, target_id):
            raise TargetProtectedByShield
        if castle is not None and castle.strength == 0:
            return
        protected = (
            await shield_service.has_active_shield(session, target_id)
            if teacher_names is None
            else await shield_service.has_active_shield(
                session, target_id, teacher_names
            )
        )
        if protected:
            raise TargetProtectedByShield

    async def _raid_mine(
        self,
        session: AsyncSession,
        target,
        *,
        loot_damage: int,
        castle_strength: int,
        attack_power: int,
        breached: bool,
    ) -> tuple[int, int]:
        """Take uncollected mine cargo only after the castle has fallen."""
        if not breached or loot_damage <= 0:
            return (0, 0)
        mine = await session.scalar(
            select(Mine).where(Mine.user_id == target.id).with_for_update()
        )
        if mine is None:
            return (0, 0)
        self.mine_service._accrue(mine)
        loot = self._loot(
            target,
            loot_damage,
            castle_strength,
            attack_power,
            coin_balance=mine.today_coin,
            diamond_balance=mine.today_diamond,
        )
        coin, diamond = loot["loot_coin"], loot["loot_diamond"]
        mine.today_coin -= coin
        mine.today_diamond -= diamond
        return coin, diamond

    async def _preview_mine_cargo(self, session: AsyncSession, target_id: int):
        mine = await session.scalar(select(Mine).where(Mine.user_id == target_id))
        if mine is None:
            return None
        cargo = SimpleNamespace(
            level=mine.level,
            last_collected_at=mine.last_collected_at,
            today=mine.today,
            daily_produced_minutes=mine.daily_produced_minutes,
            today_coin=mine.today_coin,
            today_diamond=mine.today_diamond,
            today_banana=mine.today_banana,
        )
        self.mine_service._accrue(cargo)
        return cargo

    @staticmethod
    def _credit_mine_loot(
        session: AsyncSession,
        attacker,
        loot: tuple[int, int],
        *,
        attack_id: int,
    ) -> None:
        if attacker.resources is None:
            return
        for resource_type, amount in zip(
            (ResourceType.COIN, ResourceType.DIAMOND), loot, strict=True
        ):
            if amount <= 0:
                continue
            field = resource_type.value.lower()
            before = getattr(attacker.resources, field)
            setattr(attacker.resources, field, before + amount)
            session.add(
                Transaction(
                    user_id=attacker.id,
                    resource_type=resource_type,
                    amount=amount,
                    balance_before=before,
                    balance_after=before + amount,
                    reason="ATTACK_MINE_LOOT",
                    reference_type="ATTACK",
                    reference_id=attack_id,
                )
            )

    def _loot(
        self,
        target,
        castle_damage: int,
        castle_strength: int,
        attack_power: int,
        *,
        coin_balance: int | None = None,
        diamond_balance: int | None = None,
    ) -> dict[str, int]:
        if castle_damage <= 0 or (
            target.resources is None
            and (coin_balance is None or diamond_balance is None)
        ):
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

        def amount(balance: int, resource_type: ResourceType) -> int:
            if balance <= 0 or percent <= 0:
                return 0
            percentage_amount = max(1, int(balance * percent))
            power_cap = self.config.attack_rules.loot_cap(attack_power, resource_type)
            return min(balance, percentage_amount, power_cap)

        return {
            "loot_coin": amount(
                target.resources.coin if coin_balance is None else coin_balance,
                ResourceType.COIN,
            ),
            "loot_diamond": amount(
                target.resources.diamond
                if diamond_balance is None
                else diamond_balance,
                ResourceType.DIAMOND,
            ),
            "loot_banana": self.config.attack_rules.banana_reward,
        }

    @staticmethod
    def _target_has_lootable_resources(target) -> bool:
        resources = target.resources
        return resources is not None and (resources.coin > 0 or resources.diamond > 0)

    def _empty_target_bonus(self, target, castle_damage: int) -> int:
        if castle_damage <= 0 or self._target_has_lootable_resources(target):
            return 0
        return self.config.attack_rules.empty_target_bonus_coin

    @staticmethod
    def _award_empty_target_bonus(
        session, attacker, amount: int, *, attack_id: int
    ) -> int:
        if amount <= 0 or attacker.resources is None:
            return 0
        before = attacker.resources.coin
        attacker.resources.coin = before + amount
        session.add(
            Transaction(
                user_id=attacker.id,
                resource_type=ResourceType.COIN,
                amount=amount,
                balance_before=before,
                balance_after=before + amount,
                reason="ATTACK_EMPTY_TARGET_BONUS",
                reference_type="ATTACK",
                reference_id=attack_id,
            )
        )
        return amount

    @staticmethod
    def _transfer_loot(
        session, attacker, target, loot: dict[str, int], *, attack_id: int
    ) -> None:
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
                session.add(
                    Transaction(
                        user_id=attacker.id,
                        resource_type=resource_type,
                        amount=amount,
                        balance_before=attacker_before,
                        balance_after=attacker_before + amount,
                        reason="ATTACK_XP",
                        reference_type="ATTACK",
                        reference_id=attack_id,
                    )
                )
                continue
            setattr(target.resources, field, target_before - amount)
            setattr(attacker.resources, field, attacker_before + amount)
            session.add(
                Transaction(
                    user_id=target.id,
                    resource_type=resource_type,
                    amount=-amount,
                    balance_before=target_before,
                    balance_after=target_before - amount,
                    reason="ATTACK_LOOT",
                    reference_type="ATTACK",
                    reference_id=attack_id,
                )
            )
            session.add(
                Transaction(
                    user_id=attacker.id,
                    resource_type=resource_type,
                    amount=amount,
                    balance_before=attacker_before,
                    balance_after=attacker_before + amount,
                    reason="ATTACK_LOOT",
                    reference_type="ATTACK",
                    reference_id=attack_id,
                )
            )
