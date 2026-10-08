from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import MARKDOWN_V2, bold, emoji, escape
from app.bot.custom_emojis import (
    reset_persist_group_message,
    set_persist_group_message,
)
from app.core.config import settings
from app.models.group_question import GroupQuestion
from app.models.question import Question
from app.services.question_service import QuestionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupQuestionBroadcast:
    question: Question
    publications: tuple[GroupQuestion, ...]
    sent_chat_ids: tuple[int, ...]
    failed_chat_ids: tuple[int, ...]


class GroupQuestionPublisher:
    """Creates one group question and broadcasts it to every active group."""

    def __init__(self, question_service: QuestionService | None = None) -> None:
        self.question_service = question_service or QuestionService()

    async def create_and_publish(
        self,
        bot: Bot,
        session: AsyncSession,
        *,
        question_text: str,
        correct_answer: str,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
        coin_reward: int = 0,
        diamond_reward: int = 0,
        banana_reward: int = 0,
    ) -> GroupQuestionBroadcast:
        publications = await self.question_service.create_group_question_for_all(
            session,
            question_text=question_text,
            correct_answer=correct_answer,
            expires_at=expires_at,
            published_at=published_at,
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )
        if not publications:
            raise RuntimeError("No active groups were available")

        question = publications[0].question
        sent_chat_ids: list[int] = []
        failed_chat_ids: list[int] = []
        text = self._message_text(question, expires_at)
        for publication in publications:
            chat_id = publication.group.telegram_chat_id
            try:
                for attempt in range(2):
                    try:
                        persistence = set_persist_group_message()
                        try:
                            sent_message = await bot.send_message(
                                chat_id=chat_id,
                                text=text,
                                parse_mode=MARKDOWN_V2,
                            )
                        finally:
                            reset_persist_group_message(persistence)
                        break
                    except TelegramRetryAfter as exc:
                        if attempt == 1:
                            raise
                        await asyncio.sleep(exc.retry_after)
                publication.telegram_message_id = sent_message.message_id
                await session.flush()
            except TelegramAPIError:
                logger.exception(
                    "Could not publish group question %s to chat %s",
                    question.id,
                    chat_id,
                )
                failed_chat_ids.append(chat_id)
            else:
                sent_chat_ids.append(chat_id)
            await asyncio.sleep(max(0, settings.TELEGRAM_SEND_DELAY))

        return GroupQuestionBroadcast(
            question=question,
            publications=tuple(publications),
            sent_chat_ids=tuple(sent_chat_ids),
            failed_chat_ids=tuple(failed_chat_ids),
        )

    @staticmethod
    def _message_text(question: Question, expires_at: datetime | None) -> str:
        expiration = "بدون محدودیت زمانی"
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            expiration = (
                "||"
                + expires_at.astimezone(ZoneInfo("Asia/Tehran")).strftime("%H:%M")
                + "||"
            )
        rewards = GroupQuestionPublisher._reward_lines(question)
        return (
            f"{emoji('5917916556758622836', '🔔')} "
            f"{bold('سؤال گروهی جدید')} {emoji('5253742260054409879', '✉️')}\n"
            "─────────────────────\n\n"
            f"{emoji('5825898080737697438', '❓')} {bold('سؤال')}:\n"
            f"{emoji('5235864325540815679', '↩️')}\\| « {bold(question.question_text)} »\n\n"
            f"{emoji('5825832256068918886', '📦')} {bold('پاداش پاسخ صحیح')} "
            f"{emoji('5825709849500985213', '✔️')}\n\n"
            f"{rewards}\n\n"
            "─────────────────────\n\n"
            f"{emoji('5825746176334373354', '😀')} "
            f"{bold('مهلت تا')} {expiration}"
        )

    @staticmethod
    def _reward_lines(question: Question) -> str:
        rewards: list[str] = []
        labels = (
            ("coin_reward", "سکه طلا", "5825699971076202989", "🥇"),
            ("diamond_reward", "الماس", "5825753314570018832", "💎"),
            ("banana_reward", "موز", "5902520589356113908", "🍌"),
        )
        for field, label, icon_id, fallback in labels:
            amount = getattr(question, field, 0) or 0
            if amount:
                rewards.append(
                    f"> {escape(amount)} {escape(label)} {emoji(icon_id, fallback)}"
                )
        return "\n\n".join(rewards) if rewards else "> بدون پاداش"
