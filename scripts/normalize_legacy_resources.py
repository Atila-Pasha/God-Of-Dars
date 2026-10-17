"""Normalize unmistakably inflated legacy coin/diamond balances.

Preview by default. An outlier holds over ten times 30 days of maximum mine
production (with starter floors). Applying records every reduction in the
transaction ledger and rechecks balances under row locks.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.enums import ResourceType
from app.core.game_logic import game_config
from app.db.session import AsyncSessionLocal, engine
from app.models.mine import Mine
from app.models.resource import Resource
from app.models.transaction import Transaction


def caps(mine_level: int) -> tuple[int, int]:
    mine = game_config.mine_level(mine_level)
    minutes = game_config.mine_max_catchup_minutes * 60
    return (
        max(100_000, mine.coin_per_minute * minutes),
        max(10_000, mine.diamond_per_minute * minutes),
    )


def normalized_amount(balance: int, cap: int) -> int:
    return cap if balance > cap * 10 else balance


async def run(*, apply: bool) -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Resource.user_id, Resource.coin, Resource.diamond, Mine.level)
                .outerjoin(Mine, Mine.user_id == Resource.user_id)
                .order_by(Resource.user_id)
            )
        ).all()
        candidates = [
            (user_id, mine_level or 1)
            for user_id, coin, diamond, mine_level in rows
            if coin > caps(mine_level or 1)[0] * 10
            or diamond > caps(mine_level or 1)[1] * 10
        ]
        print(f"Accounts selected: {len(candidates)}")
        if not apply:
            for user_id, mine_level in candidates:
                coin_cap, diamond_cap = caps(mine_level)
                print(
                    f"user={user_id} mine={mine_level} coin_cap={coin_cap} diamond_cap={diamond_cap}"
                )
            return

        changed = 0
        for user_id, mine_level in candidates:
            resource = await session.scalar(
                select(Resource).where(Resource.user_id == user_id).with_for_update()
            )
            if resource is None:
                continue
            for field, resource_type, cap in (
                ("coin", ResourceType.COIN, caps(mine_level)[0]),
                ("diamond", ResourceType.DIAMOND, caps(mine_level)[1]),
            ):
                before = getattr(resource, field)
                after = normalized_amount(before, cap)
                if after == before:
                    continue
                setattr(resource, field, after)
                session.add(
                    Transaction(
                        user_id=user_id,
                        resource_type=resource_type,
                        amount=after - before,
                        balance_before=before,
                        balance_after=after,
                        reason="ADMIN_BALANCE_NORMALIZATION",
                    )
                )
                changed += 1
        await session.commit()
        print(f"Balances corrected: {changed}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))
