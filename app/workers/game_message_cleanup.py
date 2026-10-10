"""Delete expired or completed group game messages using persisted DB state."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.enums import QuestionStatus
from app.db.session import AsyncSessionLocal
from app.models.chance_box import ChanceBox
from app.models.group import Group
from app.models.group_question import GroupQuestion
from app.models.question import Question

logger = logging.getLogger(__name__)


async def delete_game_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as exc:
        description = str(exc).lower()
        if (
            "message to delete not found" in description
            or "message_id_invalid" in description
        ):
            return True
        logger.warning("Could not delete game message %s: %s", message_id, exc)
        return False
    except TelegramAPIError:
        logger.exception("Could not delete game message %s", message_id)
        return False
    return True


async def process_due_game_messages(bot: Bot, *, batch_size: int = 100) -> None:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        boxes = (
            await session.execute(
                select(ChanceBox, Group.telegram_chat_id)
                .join(Group, ChanceBox.group_id == Group.id)
                .where(
                    or_(
                        ChanceBox.telegram_message_id.is_not(None),
                        ChanceBox.sticker_message_id.is_not(None),
                    ),
                    or_(
                        ChanceBox.claimed_by_user_id.is_not(None),
                        ChanceBox.expires_at <= now,
                    ),
                )
                .order_by(ChanceBox.id)
                .limit(batch_size)
                .with_for_update(of=ChanceBox, skip_locked=True)
            )
        ).all()
        for box, chat_id in boxes:
            for field in ("telegram_message_id", "sticker_message_id"):
                message_id = getattr(box, field)
                if message_id is not None and await delete_game_message(
                    bot, chat_id, message_id
                ):
                    setattr(box, field, None)

    async with AsyncSessionLocal() as session, session.begin():
        expiration = func.coalesce(GroupQuestion.expires_at, Question.expires_at)
        publications = (
            await session.execute(
                select(GroupQuestion, Group.telegram_chat_id, Question)
                .join(Group, GroupQuestion.group_id == Group.id)
                .join(Question, GroupQuestion.question_id == Question.id)
                .where(
                    GroupQuestion.telegram_message_id.is_not(None),
                    or_(
                        GroupQuestion.status != QuestionStatus.ACTIVE,
                        expiration <= now,
                    ),
                )
                .order_by(GroupQuestion.id)
                .limit(batch_size)
                .with_for_update(of=GroupQuestion, skip_locked=True)
            )
        ).all()
        for publication, chat_id, question in publications:
            expires_at = publication.expires_at or question.expires_at
            if (
                publication.status == QuestionStatus.ACTIVE
                and expires_at is not None
                and expires_at <= now
            ):
                publication.status = QuestionStatus.EXPIRED
            message_id = publication.telegram_message_id
            if message_id is not None and await delete_game_message(
                bot, chat_id, message_id
            ):
                publication.telegram_message_id = None


async def run_game_message_cleanup_worker(bot: Bot) -> None:
    while True:
        try:
            await process_due_game_messages(bot, batch_size=settings.WORKER_BATCH_SIZE)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Game message cleanup failed; retrying")
        await asyncio.sleep(max(2.0, settings.WORKER_POLL_INTERVAL))
