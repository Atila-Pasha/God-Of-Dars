from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from app.bot.keyboards.profile import level_confirmation_keyboard
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import NotificationStatus
from app.db.session import AsyncSessionLocal
from app.models.notification import Notification
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def process_due_notifications(bot: Bot, *, batch_size: int = 100) -> None:
    for _ in range(batch_size):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                notification = await NotificationService().claim_due(
                    session,
                    now=datetime.now(UTC),
                    stale_before=datetime.now(UTC)
                    - timedelta(seconds=settings.NOTIFICATION_PROCESSING_TIMEOUT_SECONDS),
                )
                if notification is None:
                    return
                notification_id = notification.id
                payload = dict(notification.payload)
                attempts = notification.attempts

        try:
            send_kwargs = {
                "chat_id": payload["chat_id"],
                "text": payload["text"],
            }
            if payload.get("level_confirmation"):
                send_kwargs["reply_markup"] = level_confirmation_keyboard()
            await bot.send_message(**send_kwargs)
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    row = await session.scalar(
                        select(Notification)
                        .where(Notification.id == notification_id)
                        .with_for_update()
                    )
                    if row is None or row.status is NotificationStatus.SENT:
                        continue
                    row.last_error = str(exc)[:500]
                    if attempts <= settings.NOTIFICATION_MAX_RETRIES:
                        row.status = NotificationStatus.PENDING
                        row.next_attempt_at = datetime.now(UTC) + timedelta(
                            seconds=settings.NOTIFICATION_RETRY_BASE_SECONDS
                            * (2 ** max(0, attempts - 1))
                        )
                    else:
                        row.status = NotificationStatus.FAILED
                        row.next_attempt_at = None
            logger.warning("Notification %s failed: %s", notification_id, exc)
            continue

        async with AsyncSessionLocal() as session:
            async with session.begin():
                row = await session.scalar(
                    select(Notification)
                    .where(Notification.id == notification_id)
                    .with_for_update()
                )
                if row is not None and row.status is not NotificationStatus.SENT:
                    row.status = NotificationStatus.SENT
                    row.sent_at = datetime.now(UTC)
                    row.next_attempt_at = None
                    row.last_error = None


async def run_notification_worker(bot: Bot) -> None:
    while True:
        try:
            await process_due_notifications(
                bot, batch_size=settings.WORKER_BATCH_SIZE
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification worker failed; retrying")
        await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
