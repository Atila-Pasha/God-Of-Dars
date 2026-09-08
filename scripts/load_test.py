"""Reproducible PostgreSQL-backed capacity probe.

This intentionally exercises the real async session and UserRepository. It is
read-only and does not call Telegram, so it can be run safely against a test
database without spamming the provider.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.resource_service import ResourceService


@dataclass(frozen=True)
class Result:
    latency_ms: float
    error: str | None = None


async def _user_ids(limit: int) -> list[int]:
    async with AsyncSessionLocal() as session:
        result = await session.scalars(
            select(User.telegram_user_id)
            .where(User.is_active.is_(True))
            .order_by(User.id)
            .limit(limit)
        )
        return list(result)


async def _operation(telegram_user_id: int, mode: str) -> Result:
    started = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            user = await UserRepository().get_by_telegram_user_id(
                session, telegram_user_id
            )
            if mode == "resource" and user is not None:
                await ResourceService.credit_coin(
                    session,
                    user.resources,
                    user_id=user.id,
                    amount=1,
                    reason="capacity_probe",
                )
                await session.rollback()
        return Result((time.perf_counter() - started) * 1000)
    except Exception as exc:  # report load failures without hiding them
        return Result((time.perf_counter() - started) * 1000, type(exc).__name__)


async def run(
    concurrency: int, operations: int, user_ids: list[int], mode: str
) -> None:
    ids = (user_ids * ((operations // len(user_ids)) + 1))[:operations]
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_operation(user_id: int) -> Result:
        async with semaphore:
            return await _operation(user_id, mode)

    started = time.perf_counter()
    results = await asyncio.gather(*(bounded_operation(user_id) for user_id in ids))
    elapsed = time.perf_counter() - started
    latencies = sorted(item.latency_ms for item in results)
    errors = [item for item in results if item.error is not None]

    def percentile(value: float) -> float:
        index = min(len(latencies) - 1, int(len(latencies) * value))
        return latencies[index]

    print(
        f"concurrency={concurrency} operations={operations} "
        f"throughput={len(results) / elapsed:.2f}/s "
        f"p50={percentile(0.50):.2f}ms p95={percentile(0.95):.2f}ms "
        f"p99={percentile(0.99):.2f}ms errors={len(errors)} "
        f"pool_checked_out={engine.pool.checkedout() if hasattr(engine.pool, 'checkedout') else 'n/a'}"
    )
    if errors:
        counts: dict[str, int] = {}
        for item in errors:
            counts[item.error or "unknown"] = counts.get(item.error or "unknown", 0) + 1
        print(f"errors_by_type={counts}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--operations", type=int, default=1000)
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--mode", choices=("read", "resource"), default="read")
    args = parser.parse_args()
    user_ids = await _user_ids(args.users)
    if not user_ids:
        raise SystemExit("No active users found in the configured PostgreSQL database")
    await run(args.concurrency, args.operations, user_ids, args.mode)


if __name__ == "__main__":
    asyncio.run(main())
