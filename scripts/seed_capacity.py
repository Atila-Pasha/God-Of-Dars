"""Seed synthetic users only in an explicitly named, disposable capacity DB."""

import asyncio

from sqlalchemy import insert
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models.castle import Castle
from app.models.defense import Defense
from app.models.resource import Resource
from app.models.user import User


async def main() -> None:
    if make_url(settings.DATABASE_URL).database != "godofdars_capacity_probe":
        raise SystemExit("Refusing to seed a non-capacity database")
    async with AsyncSessionLocal() as session, session.begin():
        ids = list(
            await session.scalars(
                insert(User).returning(User.id),
                [
                    {"telegram_user_id": 8_000_000_000 + n, "first_name": f"Load {n}"}
                    for n in range(10000)
                ],
            )
        )
        await session.execute(
            insert(Resource),
            [
                {"user_id": uid, "coin": 100000, "diamond": 1000, "banana": 1000}
                for uid in ids
            ],
        )
        castles = list(
            await session.scalars(
                insert(Castle).returning(Castle.id),
                [{"user_id": uid, "strength": 100} for uid in ids],
            )
        )
        await session.execute(
            insert(Defense), [{"castle_id": cid, "defense_power": 0} for cid in castles]
        )
    await engine.dispose()
    print("Seeded 10000 synthetic users in isolated capacity database")


if __name__ == "__main__":
    asyncio.run(main())
