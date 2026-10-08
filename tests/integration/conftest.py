"""Do not reuse asyncpg connections across pytest's per-test event loops."""

import pytest

from app.db.session import engine


@pytest.fixture(autouse=True)
async def dispose_test_pool():
    await engine.dispose()
    yield
    await engine.dispose()
