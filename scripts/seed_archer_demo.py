"""Add a small, affordable archer catalog to the local test database.

Run with ``python -m scripts.seed_archer_demo``. Existing entries are kept.
"""

import asyncio

from sqlalchemy import select

from app.core.enums import ResourceType
from app.db.session import AsyncSessionLocal, engine
from app.models.archer import Archer, ArrowPack

ARCHERS = (
    dict(name="محسنی (آزمایشی)", power=4, purchase_price=80, upgrade_price=2),
    dict(name="شفیعی (آزمایشی)", power=6, purchase_price=120, upgrade_price=3),
    dict(name="کاوه (آزمایشی)", power=8, purchase_price=180, upgrade_price=4),
)
PACKS = (
    dict(name="تیر ساده (آزمایشی)", power=2, quantity=2, purchase_price=15),
    dict(name="تیر فولادی (آزمایشی)", power=4, quantity=3, purchase_price=35),
    dict(name="تیر افسانه‌ای (آزمایشی)", power=7, quantity=5, purchase_price=90),
)


async def main() -> None:
    try:
        async with AsyncSessionLocal() as session:
            for model, entries in ((Archer, ARCHERS), (ArrowPack, PACKS)):
                for entry in entries:
                    exists = await session.scalar(
                        select(model.id).where(model.name == entry["name"])
                    )
                    if exists is not None:
                        continue
                    values = dict(entry)
                    values.update(
                        purchase_resource=ResourceType.COIN,
                        unlock_level=1,
                        description="مورد آزمایشی برای تست سیستم کماندارها",
                    )
                    if model is Archer:
                        values["emoji"] = "5314526780416092636"
                    session.add(model(**values))
            await session.commit()
            for model in (Archer, ArrowPack):
                rows = (
                    await session.scalars(
                        select(model)
                        .where(model.name.like("%آزمایشی%"))
                        .order_by(model.id)
                    )
                ).all()
                print(model.__name__, [(row.id, row.name) for row in rows])
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
