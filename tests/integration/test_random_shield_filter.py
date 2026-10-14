from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.session import AsyncSessionLocal
from app.models.castle import Castle
from app.models.defense import Defense
from app.models.user import User
from app.repositories.user import UserRepository


@pytest.mark.asyncio
async def test_random_picker_excludes_free_shield_and_missing_castle() -> None:
    async with AsyncSessionLocal() as session:
        transaction = await session.begin()
        try:
            unique_level = 1_000_000 + uuid4().int % 1_000_000

            def player(*, protected: bool = False, has_castle: bool = True) -> User:
                user = User(
                    telegram_user_id=uuid4().int % 2_000_000_000,
                    first_name="random target",
                    level=unique_level,
                    free_shield_until=(
                        datetime.now(UTC) + timedelta(hours=1) if protected else None
                    ),
                )
                if has_castle:
                    user.castle = Castle(
                        strength=100, defense=Defense(defense_power=20)
                    )
                return user

            attacker = player()
            shielded = player(protected=True)
            without_castle = player(has_castle=False)
            eligible = player()
            session.add_all((attacker, shielded, without_castle, eligible))
            await session.flush()

            repository = UserRepository()
            levels = await repository.list_active_levels_by_proximity(
                session, level=unique_level, exclude_user_id=attacker.id
            )
            target = await repository.pick_random_active_at_level(
                session, level=unique_level, exclude_user_id=attacker.id
            )

            assert levels[0] == unique_level
            assert target.id == eligible.id
        finally:
            await transaction.rollback()
