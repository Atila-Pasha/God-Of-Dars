"""Real Dispatcher/PostgreSQL load test with a local Telegram transport.

The application dispatcher, middleware, handlers, SQLAlchemy sessions and
PostgreSQL are real. Only Telegram's HTTP transport is replaced. The default
scenarios are read-heavy previews/menu flows so the test database is not
silently modified by thousands of purchases or attacks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import (
    Chat,
    ChatMemberMember,
    Message,
    Update,
)
from aiogram.types import (
    User as TelegramUser,
)
from sqlalchemy import select, text

from app.bot import create_dispatcher
from app.db.session import AsyncSessionLocal, engine
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher

SCENARIOS = (
    "start",
    "callback",
    "attack",
    "purchase",
    "upgrade",
    "daily",
    "notification",
    "broadcast",
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def scenario_list(value: str) -> tuple[str, ...]:
    scenarios = tuple(item.strip() for item in value.split(",") if item.strip())
    invalid = sorted(set(scenarios) - set(SCENARIOS))
    if not scenarios or invalid:
        choices = ", ".join(SCENARIOS)
        detail = f"invalid scenarios: {', '.join(invalid)}; " if invalid else ""
        raise argparse.ArgumentTypeError(f"{detail}choose from: {choices}")
    return scenarios


_dispatcher = None


@dataclass
class Sample:
    latency_ms: float
    error: str | None
    scenario: str


class FakeTelegramSession(BaseSession):
    """Deterministic Bot API substitute with configurable latency/failures."""

    def __init__(self, latency_ms: float = 20.0) -> None:
        super().__init__()
        self.latency = latency_ms / 1000
        self.calls = Counter()
        self.wait_ms = 0.0

    async def make_request(
        self, bot: Bot, method: TelegramMethod, timeout: int | None = None
    ):
        started = monotonic()
        self.calls[method.__api_method__] += 1
        await asyncio.sleep(self.latency)
        self.wait_ms += (monotonic() - started) * 1000
        name = method.__api_method__
        if name == "getChatMember":
            return ChatMemberMember(
                user=TelegramUser(id=method.user_id, is_bot=False, first_name="load")
            )
        if name in {"deleteMessage", "answerCallbackQuery", "sendChatAction"}:
            return True
        if name == "getMe":
            return TelegramUser(id=999999, is_bot=True, first_name="loadbot")
        return Message(
            message_id=self.calls["messages"],
            date=datetime.now(UTC),
            chat=Chat(id=getattr(method, "chat_id", -100), type="private"),
        )

    async def close(self) -> None:
        return None

    async def stream_content(self, url, timeout=30, chunk_size=65536):
        if False:
            yield b""


async def load_fixtures(limit: int) -> tuple[list[TelegramUser], str]:
    async with AsyncSessionLocal() as session:
        rows = list(
            (
                await session.execute(
                    select(
                        User.telegram_user_id,
                        User.username,
                        User.first_name,
                        User.last_name,
                    )
                    .where(User.is_active.is_(True))
                    .order_by(User.id)
                    .limit(limit)
                )
            ).all()
        )
        users = [
            TelegramUser(
                id=row.telegram_user_id,
                is_bot=False,
                first_name=row.first_name,
                last_name=row.last_name,
                username=row.username,
            )
            for row in rows
        ]
        teacher = await session.scalar(
            select(Teacher.name)
            .join(UserTeacher, UserTeacher.teacher_id == Teacher.id)
            .join(User, User.id == UserTeacher.user_id)
            .where(User.is_active.is_(True))
            .order_by(User.id)
            .limit(1)
        )
    if not users:
        raise RuntimeError("No active users found in PostgreSQL")
    return users, teacher or "افلاطون"


def make_update(update_id: int, user: TelegramUser, scenario: str) -> Update:
    chat = Chat(id=user.id, type="private")
    message = Message(
        message_id=update_id,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text={
            "start": "/start",
            "callback": "/profile",
            "attack": "/attack",
            "purchase": "خرید سپر",
            "upgrade": "پروفایل",
            "daily": "فعالیت‌های روزانه",
            "notification": "/stat",
            "broadcast": "/help",
        }[scenario],
    )
    return Update(update_id=update_id, message=message)


async def one(
    dispatcher,
    bot: Bot,
    update: Update,
    scenario: str,
    semaphore: asyncio.Semaphore,
) -> Sample:
    async with semaphore:
        started = monotonic()
        try:
            await dispatcher.feed_update(bot, update)
            return Sample((monotonic() - started) * 1000, None, scenario)
        except Exception as exc:
            return Sample(
                (monotonic() - started) * 1000,
                type(exc).__name__,
                scenario,
            )


async def db_snapshot() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        pool = engine.pool
        values = {
            "pool_checked_out": pool.checkedout()
            if hasattr(pool, "checkedout")
            else -1,
            "notifications_pending": (
                await session.execute(
                    text(
                        "select count(*) from notifications "
                        "where status in ('PENDING','PROCESSING')"
                    )
                )
            ).scalar_one(),
            "db_lock_waiting": (
                await session.execute(
                    text(
                        "select count(*) from pg_stat_activity "
                        "where wait_event_type = 'Lock'"
                    )
                )
            ).scalar_one(),
        }
    return values


async def run_level(
    concurrency: int,
    operations: int,
    scenarios: tuple[str, ...],
    latency_ms: float,
) -> None:
    users, _ = await load_fixtures(max(operations, 100))
    global _dispatcher
    session = FakeTelegramSession(latency_ms)
    bot = Bot("123456:LOADTEST", session=session)
    if _dispatcher is None:
        _dispatcher = create_dispatcher()
    semaphore = asyncio.Semaphore(concurrency)
    jobs = [
        one(
            _dispatcher,
            bot,
            make_update(
                index, users[index % len(users)], scenarios[index % len(scenarios)]
            ),
            scenarios[index % len(scenarios)],
            semaphore,
        )
        for index in range(operations)
    ]
    started = monotonic()
    samples = await asyncio.gather(*jobs)
    elapsed = monotonic() - started
    latencies = sorted(sample.latency_ms for sample in samples)
    errors = [sample for sample in samples if sample.error]

    def pct(value: float) -> float:
        return latencies[min(len(latencies) - 1, int(len(latencies) * value))]

    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(
        json.dumps(
            {
                "concurrency": concurrency,
                "operations": operations,
                "throughput": len(samples) / elapsed,
                "p50_ms": pct(0.50),
                "p95_ms": pct(0.95),
                "p99_ms": pct(0.99),
                "error_rate": len(errors) / len(samples),
                "errors": dict(Counter(item.error for item in errors)),
                "telegram_calls": sum(session.calls.values()),
                "telegram_wait_ms": session.wait_ms,
                "rss_mb": rss_mb,
                "db": await db_snapshot(),
                "scenarios": dict(Counter(sample.scenario for sample in samples)),
            },
            ensure_ascii=False,
        )
    )
    await bot.session.close()


async def run_sustained(
    concurrency: int,
    duration_seconds: int,
    interval_seconds: float,
    latency_ms: float,
) -> None:
    started = monotonic()
    batch = 0
    while monotonic() - started < duration_seconds:
        batch += 1
        await run_level(
            concurrency,
            max(concurrency, 25),
            (
                "start",
                "callback",
                "attack",
                "purchase",
                "upgrade",
                "daily",
                "notification",
                "broadcast",
            ),
            latency_ms,
        )
        await asyncio.sleep(max(0, interval_seconds))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=positive_int, required=True)
    parser.add_argument("--operations", type=positive_int, default=1000)
    parser.add_argument("--latency-ms", type=nonnegative_float, default=20)
    parser.add_argument("--duration-seconds", type=nonnegative_int, default=0)
    parser.add_argument("--interval-seconds", type=nonnegative_float, default=10)
    parser.add_argument(
        "--scenarios",
        type=scenario_list,
        default=SCENARIOS,
    )
    args = parser.parse_args()
    if args.duration_seconds:
        await run_sustained(
            args.concurrency,
            args.duration_seconds,
            args.interval_seconds,
            args.latency_ms,
        )
    else:
        await run_level(
            args.concurrency,
            args.operations,
            args.scenarios,
            args.latency_ms,
        )


if __name__ == "__main__":
    asyncio.run(main())
