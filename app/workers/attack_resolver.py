from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, SQLAlchemyError

from app.bot.keyboards.profile import level_confirmation_keyboard
from app.bot.utils.attack import teacher_phrase
from app.core.enums import AttackStatus
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.attack import Attack
from app.repositories.user import UserRepository
from app.services.attack_service import AttackService
from app.services.level_service import LevelService
from app.services.school_errors import OperationNotConfigured
from app.services.school_errors import SchoolError

logger = logging.getLogger(__name__)
level_service = LevelService()
user_repository = UserRepository()


def _result_text(result) -> str:
    injury = (
        f"🩹 آسیب دبیر: {result.teacher_injury}"
        if result.teacher_injury
        else "🛡 دژ نتوانست به دبیر آسیب بزند."
    )
    return (
        f"⚔️ حمله به دژ «{result.target_name}» تمام شد!\n\n"
        f"👨‍🏫 {teacher_phrase(result.teacher_name)}\n"
        f"💥 تخریب دژ: {result.castle_damage}\n"
        f"🏰 قدرت باقی‌مانده دژ: {result.castle_strength_after}\n"
        f"{injury}\n"
        f"🎁 غنیمت: 🪙 {result.loot_coin}  💎 {result.loot_diamond}  "
        f"🍌 موز {result.loot_banana}"
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
                        Attack.status.in_(
                            (AttackStatus.PENDING, AttackStatus.FAILED)
                        ),
                    )
                    .values(
                        status=AttackStatus.PROCESSING,
                        processing_at=now,
                    )
                )
        for attack_id in attack_ids:
            try:
                async with session.begin():
                    result = await AttackService().resolve_pending_attack(
                        session, attack_id
                    )
                    can_upgrade = (
                        result is not None
                        and await _can_upgrade_level(
                            session, result.attacker_telegram_id
                        )
                    )
                if result is None:
                    continue
                text = _result_text(result)
                try:
                    await bot.send_message(result.attacker_telegram_id, text)
                    if can_upgrade:
                        await bot.send_message(
                            result.attacker_telegram_id,
                            "🎉 موز کافی داری!\n"
                            "الان می‌تونی سطح کاربریت رو بالا ببری.",
                            reply_markup=level_confirmation_keyboard(),
                        )
                except TelegramAPIError:
                    logger.info(
                        "Could not notify attacker for attack %s", attack_id
                    )
                try:
                    await bot.send_message(
                        result.target_telegram_id,
                        f"🎯 شما مورد حمله قرار گرفتید!\n\n{text}",
                    )
                except TelegramAPIError:
                    logger.info("Could not notify target for attack %s", attack_id)
            except SQLAlchemyError as exc:
                logger.exception("Could not resolve attack %s", attack_id)
                await _record_failure(session, attack_id, exc)
            except SchoolError as exc:
                logger.error("Attack %s has an invalid game state: %s", attack_id, exc)
                await _record_failure(session, attack_id, exc)


def _is_retryable(exc: SQLAlchemyError) -> bool:
    if isinstance(exc, IntegrityError):
        return False
    if not isinstance(exc, (OperationalError, DBAPIError)):
        return False
    code = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return code in {"40001", "40P01"} or isinstance(exc, OperationalError)


async def _record_failure(
    session, attack_id: int, exc: Exception
) -> None:
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
            delay = settings.ATTACK_RETRY_BASE_SECONDS * (
                2 ** (attack.retry_count - 1)
            )
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