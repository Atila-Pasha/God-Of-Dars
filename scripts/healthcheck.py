"""Container health check: verify that PostgreSQL accepts a trivial query."""

from __future__ import annotations

import asyncio
from time import time

from sqlalchemy import text

from app.core.runtime_health import HEARTBEAT
from app.db.session import engine


async def main() -> None:
    if not HEARTBEAT.exists() or time() - float(HEARTBEAT.read_text()) > 30:
        raise RuntimeError("Application event-loop heartbeat is stale")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
