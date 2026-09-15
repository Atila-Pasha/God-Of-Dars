"""Container health check: verify that PostgreSQL accepts a trivial query."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
