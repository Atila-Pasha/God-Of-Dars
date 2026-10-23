"""Resumable admin broadcasts with short database transactions."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import BufferedInputFile
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.broadcast_job import BroadcastJob
from app.models.user import User

logger = logging.getLogger(__name__)


def status_text(job: BroadcastJob) -> str:
    processed = job.sent + job.failed
    if job.status == "COMPLETED":
        heading = "✅ پیام همگانی تمام شد."
    elif job.status == "FAILED":
        heading = "⚠️ ارسال پیام همگانی متوقف شد."
    elif job.status == "PENDING":
        heading = "📣 پیام همگانی در صف ارسال است."
    else:
        heading = "📣 ارسال پیام همگانی در حال انجام است."
    lines = [
        heading,
        f"شناسه ارسال: {job.id}",
        f"کل کاربران: {job.total}",
        f"بررسی‌شده: {processed} از {job.total}",
        f"موفق: {job.sent}",
        f"ناموفق: {job.failed}",
    ]
    if job.status == "FAILED" and job.last_error:
        lines.append(f"خطا: {job.last_error[:200]}")
    return "\n".join(lines)


async def _pause(seconds: float, stop_event: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0, seconds))
    except TimeoutError:
        return
    raise asyncio.CancelledError


async def _send_one(
    main_bot: Bot, job: BroadcastJob, chat_id: int, stop_event: asyncio.Event
) -> str | None:
    for attempt in range(3):
        try:
            if job.photo_file_id is not None or job.photo_data is not None:
                photo = job.photo_file_id or BufferedInputFile(
                    job.photo_data or b"", filename="broadcast.jpg"
                )
                sent = await main_bot.send_photo(
                    chat_id=chat_id, photo=photo, caption=job.caption
                )
                return sent.photo[-1].file_id if sent.photo else job.photo_file_id
            if job.text is None:
                raise ValueError("Broadcast text is missing")
            await main_bot.send_message(chat_id=chat_id, text=job.text)
            return None
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            await _pause(exc.retry_after + 0.5, stop_event)
    return None


async def _process_page(main_bot: Bot, job_id: int, stop_event: asyncio.Event) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(BroadcastJob, job_id, with_for_update=True)
        if job is None or job.status not in {"PENDING", "RUNNING"}:
            return
        job.status = "RUNNING"
        recipients = (
            await session.execute(
                select(User.id, User.telegram_user_id)
                .where(
                    User.id > job.last_user_id,
                    User.id <= job.max_user_id,
                    User.telegram_user_id > 0,
                )
                .order_by(User.id)
                .limit(settings.BROADCAST_BATCH_SIZE)
            )
        ).all()
        if not recipients:
            job.failed += max(0, job.total - job.sent - job.failed)
            job.status = "COMPLETED"
            job.finished_at = datetime.now(UTC)
            job.photo_data = None
        await session.commit()
    if not recipients:
        return

    for user_id, telegram_id in recipients:
        if stop_event.is_set():
            return
        file_id = None
        success = False
        error = None
        try:
            file_id = await _send_one(main_bot, job, telegram_id, stop_event)
            success = True
        except asyncio.CancelledError:
            raise
        except (TelegramAPIError, OSError, TimeoutError, ValueError) as exc:
            error = str(exc)
            logger.warning("Broadcast %s to %s failed: %s", job_id, telegram_id, exc)
        async with AsyncSessionLocal() as session:
            progress = await session.get(BroadcastJob, job_id, with_for_update=True)
            if progress is None or progress.last_user_id >= user_id:
                continue
            progress.last_user_id = user_id
            if success:
                progress.sent += 1
                if file_id and not progress.photo_file_id:
                    progress.photo_file_id = file_id
                    progress.photo_data = None
                    job.photo_file_id = file_id
                    job.photo_data = None
            else:
                progress.failed += 1
                progress.last_error = (error or "نامشخص")[:500]
            await session.commit()
        await _pause(settings.TELEGRAM_SEND_DELAY, stop_event)


async def _send_pending_report(admin_bot: Bot) -> bool:
    async with AsyncSessionLocal() as session:
        job = await session.scalar(
            select(BroadcastJob)
            .where(
                BroadcastJob.status.in_(("COMPLETED", "FAILED")),
                BroadcastJob.report_sent_at.is_(None),
            )
            .order_by(BroadcastJob.id)
            .limit(1)
        )
        if job is None:
            return False
        job_id = job.id
        chat_id = job.admin_chat_id
        text = status_text(job)
    await admin_bot.send_message(chat_id=chat_id, text=text)
    async with AsyncSessionLocal() as session:
        job = await session.get(BroadcastJob, job_id, with_for_update=True)
        if job is not None and job.report_sent_at is None:
            job.report_sent_at = datetime.now(UTC)
            await session.commit()
    return True


async def run_broadcast_worker(
    admin_bot: Bot, stop_event: asyncio.Event | None = None
) -> None:
    stop_event = stop_event or asyncio.Event()
    session = AiohttpSession(
        proxy=settings.TELEGRAM_PROXY, limit=settings.TELEGRAM_HTTP_LIMIT
    )
    async with Bot(token=settings.BOT_TOKEN, session=session) as main_bot:
        while not stop_event.is_set():
            job_id: int | None = None
            try:
                async with AsyncSessionLocal() as db:
                    job_id = await db.scalar(
                        select(BroadcastJob.id)
                        .where(BroadcastJob.status.in_(("PENDING", "RUNNING")))
                        .order_by(BroadcastJob.id)
                        .limit(1)
                    )
                if job_id is not None:
                    await _process_page(main_bot, job_id, stop_event)
                    continue
                if await _send_pending_report(admin_bot):
                    continue
                await _pause(2, stop_event)
            except asyncio.CancelledError:
                break
            except TelegramAPIError:
                logger.exception("Could not deliver broadcast completion report")
                await _pause(5, stop_event)
            except Exception as exc:
                logger.exception("Broadcast worker failed")
                if job_id is not None:
                    async with AsyncSessionLocal() as db:
                        job = await db.get(BroadcastJob, job_id, with_for_update=True)
                        if job is not None and job.status in {"PENDING", "RUNNING"}:
                            job.status = "FAILED"
                            job.finished_at = datetime.now(UTC)
                            job.last_error = str(exc)[:500]
                            await db.commit()
                await _pause(5, stop_event)
