from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.group_question_publisher import GroupQuestionPublisher
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.library_errors import GroupNotFound


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and broadcast a group question."
    )
    parser.add_argument("--question", help="Question text")
    parser.add_argument("--answer", help="Correct answer")
    parser.add_argument(
        "--hours",
        type=float,
        default=24,
        help="How many hours the question stays available (default: 24)",
    )
    parser.add_argument(
        "--coins", "--coin-reward", "--gold", "--gold-reward",
        dest="coin_reward", type=int,
        help="Coin reward (asks interactively when omitted)",
    )
    parser.add_argument(
        "--diamonds", "--diamond-reward", dest="diamond_reward", type=int,
        help="Diamond reward (asks interactively when omitted)",
    )
    parser.add_argument(
        "--bananas", "--banana-reward", dest="banana_reward", type=int,
        help="Banana reward (asks interactively when omitted)",
    )
    return parser.parse_args()


def required_input(value: str | None, prompt: str) -> str:
    result = value.strip() if value else input(prompt).strip()
    if not result:
        raise ValueError("متن سؤال و پاسخ صحیح نمی‌توانند خالی باشند.")
    return result


def reward_input(value: int | None, prompt: str) -> int:
    raw_value = str(value) if value is not None else input(prompt).strip()
    if not raw_value:
        return 0
    try:
        amount = int(raw_value)
    except ValueError as exc:
        raise ValueError("مقدار پاداش باید یک عدد صحیح باشد.") from exc
    if amount < 0:
        raise ValueError("مقدار پاداش نمی‌تواند منفی باشد.")
    return amount


async def main() -> None:
    args = parse_args()
    if args.hours <= 0:
        raise ValueError("مدت اعتبار باید بیشتر از صفر باشد.")

    question_text = required_input(args.question, "متن سؤال گروهی: ")
    correct_answer = required_input(args.answer, "پاسخ صحیح: ")
    coin_reward = reward_input(args.coin_reward, "مقدار طلا (خالی = بدون پاداش): ")
    diamond_reward = reward_input(
        args.diamond_reward, "تعداد الماس (خالی = بدون پاداش): "
    )
    banana_reward = reward_input(
        args.banana_reward, "تعداد موز (خالی = بدون پاداش): "
    )
    expires_at = datetime.now(UTC) + timedelta(hours=args.hours)
    bot_session = (
        AiohttpSession(proxy=settings.TELEGRAM_PROXY)
        if settings.TELEGRAM_PROXY
        else None
    )

    async with (
        Bot(token=settings.BOT_TOKEN, session=bot_session) as bot,
        AsyncSessionLocal() as session,
        session.begin(),
    ):
        result = await GroupQuestionPublisher().create_and_publish(
            bot,
            session,
            question_text=question_text,
            correct_answer=correct_answer,
            expires_at=expires_at,
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )

    print("✅ سؤال گروهی ساخته و ارسال شد.")
    print(f"شناسه سؤال: {result.question.id}")
    print(f"سؤال: {result.question.question_text}")
    print(f"پاسخ صحیح: {result.question.correct_answer}")
    print(
        "پاداش: "
        f"{result.question.coin_reward} طلا، "
        f"{result.question.diamond_reward} الماس، "
        f"{result.question.banana_reward} موز"
    )
    print(f"گروه‌های دریافت‌کننده: {len(result.sent_chat_ids)}")
    if result.failed_chat_ids:
        print(f"گروه‌های ناموفق: {result.failed_chat_ids}")
    print(f"اعتبار تا: {expires_at.isoformat()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except GroupNotFound as exc:
        raise SystemExit("❌ هیچ گروه فعالی برای ارسال سؤال ثبت نشده است.") from exc
    except (ValueError, EOFError) as exc:
        raise SystemExit(f"❌ {exc}") from exc
