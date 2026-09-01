from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from app.db.session import AsyncSessionLocal
from app.services.question_service import QuestionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an active daily question in the database."
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

    question_text = required_input(args.question, "متن سؤال روزانه: ")
    correct_answer = required_input(args.answer, "پاسخ صحیح: ")
    coin_reward = reward_input(args.coin_reward, "مقدار طلا (خالی = بدون پاداش): ")
    diamond_reward = reward_input(
        args.diamond_reward, "تعداد الماس (خالی = بدون پاداش): "
    )
    banana_reward = reward_input(
        args.banana_reward, "تعداد موز (خالی = بدون پاداش): "
    )
    expires_at = datetime.now(UTC) + timedelta(hours=args.hours)

    async with AsyncSessionLocal() as session, session.begin():
        question = await QuestionService().create_daily_question(
            session,
            question_text=question_text,
            correct_answer=correct_answer,
            expires_at=expires_at,
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )

    print("✅ سؤال روزانه با موفقیت ساخته شد.")
    print(f"شناسه: {question.id}")
    print(f"سؤال: {question.question_text}")
    print(f"پاسخ صحیح: {question.correct_answer}")
    print(
        "پاداش: "
        f"{question.coin_reward} طلا، "
        f"{question.diamond_reward} الماس، "
        f"{question.banana_reward} موز"
    )
    print(f"اعتبار تا: {expires_at.isoformat()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, EOFError) as exc:
        raise SystemExit(f"❌ {exc}") from exc
