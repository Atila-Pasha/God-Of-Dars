from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from sqlalchemy import select

from app.bot.keyboards.profile import level_confirmation_keyboard
from app.core.config import settings
from app.core.enums import NotificationStatus
from app.db.session import AsyncSessionLocal
from app.models.notification import Notification
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def process_due_notifications(bot: Bot, *, batch_size: int = 100) -> None:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        notifications = await NotificationService().claim_due_batch(
            session,
            now=now,
            stale_before=now
            - timedelta(seconds=settings.NOTIFICATION_PROCESSING_TIMEOUT_SECONDS),
            batch_size=batch_size,
        )
    if not notifications:
        return

    send_limit = asyncio.Semaphore(settings.NOTIFICATION_SEND_CONCURRENCY)
    await asyncio.gather(
        *(
            _deliver_notification(bot, notification, send_limit)
            for notification in notifications
        )
    )


async def _deliver_notification(
    bot: Bot, notification: Notification, send_limit: asyncio.Semaphore
) -> None:
    notification_id = notification.id
    payload = dict(notification.payload)
    attempts = notification.attempts

    try:
        async with send_limit:
            send_kwargs = {
                "chat_id": payload["chat_id"],
                "text": payload["text"],
            }
            if payload.get("level_confirmation"):
                send_kwargs["reply_markup"] = level_confirmation_keyboard()
            await bot.send_message(**send_kwargs)
    except Exception as exc:
        async with AsyncSessionLocal() as session, session.begin():
            row = await session.scalar(
                select(Notification)
                .where(Notification.id == notification_id)
                .with_for_update()
            )
            if row is None or row.status is NotificationStatus.SENT:
                return
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
        return

    async with AsyncSessionLocal() as session, session.begin():
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


async def run_notification_worker(bot: Bot, *, worker_id: int = 0) -> None:
    while True:
        try:
            await process_due_notifications(bot, batch_size=settings.WORKER_BATCH_SIZE)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification worker %s failed; retrying", worker_id)
        await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
