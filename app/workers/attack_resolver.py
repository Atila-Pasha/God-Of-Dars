from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.bot.utils.attack import teacher_phrase
from app.core.enums import AttackStatus
from app.db.session import AsyncSessionLocal
from app.models.attack import Attack
from app.services.attack_service import AttackService

logger = logging.getLogger(__name__)


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
        async with session.begin():
            attack_ids = list(
                await session.scalars(
                    select(Attack.id)
                    .where(
                        Attack.status == AttackStatus.PENDING,
                        Attack.resolve_at <= datetime.now(UTC),
                    )
                    .order_by(Attack.resolve_at, Attack.id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
        for attack_id in attack_ids:
            try:
                async with session.begin():
                    result = await AttackService().resolve_pending_attack(
                        session, attack_id
                    )
                if result is None:
                    continue
                text = _result_text(result)
                await bot.send_message(result.attacker_telegram_id, text)
                try:
                    await bot.send_message(
                        result.target_telegram_id,
                        f"🎯 شما مورد حمله قرار گرفتید!\n\n{text}",
                    )
                except TelegramAPIError:
                    logger.info("Could not notify target for attack %s", attack_id)
            except SQLAlchemyError:
                logger.exception("Could not resolve attack %s", attack_id)


async def run_attack_resolver(bot: Bot) -> None:
    while True:
        await resolve_due_attacks(bot)
        await asyncio.sleep(2)