from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.bot.banners import MARKDOWN_V2, attack_result_banner
from app.core.config import settings
from app.core.enums import AttackStatus
from app.db.session import AsyncSessionLocal
from app.models.attack import Attack
from app.models.user_teacher import UserTeacher
from app.repositories.user import UserRepository
from app.services.attack_service import AttackService
from app.services.level_service import LevelService
from app.services.notification_service import NotificationService
from app.services.school_errors import OperationNotConfigured, SchoolError

logger = logging.getLogger(__name__)
level_service = LevelService()
user_repository = UserRepository()
notification_service = NotificationService()


def _result_text(result, *, recipient: str = "attacker") -> str:
    return attack_result_banner(result, recipient=recipient)


async def _command_result(session, result):
    """Create one complete report after every teacher in a command has resolved."""
    command_id = result.attack.attack_command_id
    if command_id is None:
        return result
    records = list(
        await session.scalars(
            select(Attack)
            .where(Attack.attack_command_id == command_id)
            .options(selectinload(Attack.teacher).selectinload(UserTeacher.teacher))
            .order_by(Attack.id)
        )
    )
    if not records or any(row.status is not AttackStatus.RESOLVED for row in records):
        return None
    details = tuple(
        (
            row.teacher_name_snapshot
            or (row.teacher.teacher.name if row.teacher is not None else "دبیر"),
            row.teacher_ability_snapshot
            or (row.teacher.teacher.ability_text if row.teacher is not None else None),
            row.teacher_emoji_snapshot
            or (row.teacher.teacher.emoji if row.teacher is not None else None),
        )
        for row in records
    )
    return replace(
        result,
        teacher_name="، ".join(name for name, _, _ in details),
        teacher_details=details,
        castle_damage=sum(row.result_damage or 0 for row in records),
        teacher_injury=sum(row.result_teacher_injury for row in records),
        loot_coin=sum(row.loot_coin for row in records),
        loot_diamond=sum(row.loot_diamond for row in records),
        loot_banana=sum(row.loot_banana for row in records),
        castle_strength_before=records[0].target_castle_strength_snapshot,
        source_chat_id=records[0].source_chat_id,
        blocked_by_shield=all((row.result_damage or 0) == 0 for row in records)
        and result.blocked_by_shield,
    )


async def resolve_due_attacks(bot: Bot, *, batch_size: int = 100) -> None:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        stale_processing = now - timedelta(
            seconds=settings.ATTACK_PROCESSING_TIMEOUT_SECONDS
        )
        async with session.begin():
            attack_ids = list(
                await session.scalars(
                    select(Attack.id)
                    .where(
                        (
                            (Attack.status == AttackStatus.PENDING)
                            & (Attack.resolve_at <= now)
                        )
                        | (
                            (Attack.status == AttackStatus.FAILED)
                            & (Attack.next_retry_at <= now)
                        )
                        | (
                            (Attack.status == AttackStatus.PROCESSING)
                            & (Attack.processing_at <= stale_processing)
                        )
                    )
                    .order_by(Attack.resolve_at, Attack.id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            if attack_ids:
                await session.execute(
                    update(Attack)
                    .where(
                        Attack.id.in_(attack_ids),
                        Attack.status.in_((AttackStatus.PENDING, AttackStatus.FAILED)),
                    )
                    .values(
                        status=AttackStatus.PROCESSING,
                        processing_at=now,
                    )
                )
        for attack_id in attack_ids:
            try:
                async with session.begin():
                    command_id = await session.scalar(
                        select(Attack.attack_command_id).where(Attack.id == attack_id)
                    )
                    if command_id is not None:
                        # Every worker resolving the same command takes this lock
                        # before touching its row, so the final report is complete.
                        await session.execute(
                            select(
                                func.pg_advisory_xact_lock(func.hashtext(command_id))
                            )
                        )
                    result = await AttackService().resolve_pending_attack(
                        session, attack_id
                    )
                    if result is not None:
                        result = await _command_result(session, result)
                    can_upgrade = result is not None and await _can_upgrade_level(
                        session, result.attacker_telegram_id
                    )
                    if result is not None:
                        key = command_id or str(attack_id)
                        text = _result_text(result)
                        await notification_service.enqueue(
                            session,
                            notification_type="ATTACK_RESULT",
                            recipient_user_id=result.attack.attacker_id,
                            idempotency_key=f"ATTACK_RESULT:{key}:ATTACKER",
                            payload={
                                "chat_id": result.attacker_telegram_id,
                                "text": text,
                                "parse_mode": MARKDOWN_V2,
                            },
                        )
                        await notification_service.enqueue(
                            session,
                            notification_type="ATTACK_RESULT",
                            recipient_user_id=result.attack.target_id,
                            idempotency_key=f"ATTACK_RESULT:{key}:TARGET",
                            payload={
                                "chat_id": result.target_telegram_id,
                                "text": _result_text(result, recipient="defender"),
                                "parse_mode": MARKDOWN_V2,
                            },
                        )
                        if result.source_chat_id is not None:
                            await notification_service.enqueue(
                                session,
                                notification_type="ATTACK_RESULT",
                                recipient_user_id=result.attack.attacker_id,
                                idempotency_key=f"ATTACK_RESULT:{key}:GROUP",
                                payload={
                                    "chat_id": result.source_chat_id,
                                    "text": text,
                                    "parse_mode": MARKDOWN_V2,
                                },
                            )
                        if can_upgrade:
                            await notification_service.enqueue(
                                session,
                                notification_type="LEVEL_UP_AVAILABLE",
                                recipient_user_id=result.attack.attacker_id,
                                idempotency_key=f"ATTACK_LEVEL_UP:{key}:ATTACKER",
                                payload={
                                    "chat_id": result.attacker_telegram_id,
                                    "text": "🎉 موز کافی داری!\nالان می‌تونی سطح کاربریت رو بالا ببری.",
                                    "level_confirmation": True,
                                },
                            )
                if result is None:
                    continue
            except SQLAlchemyError as exc:
                logger.exception("Could not resolve attack %s", attack_id)
                await _record_failure(session, attack_id, exc)
            except SchoolError as exc:
                logger.error("Attack %s has an invalid game state: %s", attack_id, exc)
                await _record_failure(session, attack_id, exc)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, IntegrityError):
        return False
    if not isinstance(exc, (OperationalError, DBAPIError)):
        return False
    code = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return code in {"40001", "40P01"} or isinstance(exc, OperationalError)


async def _record_failure(session, attack_id: int, exc: Exception) -> None:
    async with session.begin():
        attack = await session.scalar(
            select(Attack).where(Attack.id == attack_id).with_for_update()
        )
        if attack is None or attack.status is not AttackStatus.PROCESSING:
            return
        attack.retry_count += 1
        attack.failed_at = datetime.now(UTC)
        attack.last_error = str(exc)[:500]
        if _is_retryable(exc) and attack.retry_count <= settings.ATTACK_MAX_RETRIES:
            delay = settings.ATTACK_RETRY_BASE_SECONDS * (2 ** (attack.retry_count - 1))
            attack.status = AttackStatus.FAILED
            attack.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        else:
            attack.status = AttackStatus.FAILED
            attack.next_retry_at = None


async def _can_upgrade_level(
    session,
    telegram_user_id: int,
) -> bool:
    user = await user_repository.get_by_telegram_user_id(session, telegram_user_id)
    if user is None or user.resources is None:
        return False
    if user.level >= level_service.config.level_progression.max_level:
        return False
    try:
        cost = level_service.upgrade_cost(user.level)
    except OperationNotConfigured:
        return False
    return user.resources.banana >= cost


async def run_attack_resolver(bot: Bot) -> None:
    while True:
        await resolve_due_attacks(bot)
        await asyncio.sleep(2)
