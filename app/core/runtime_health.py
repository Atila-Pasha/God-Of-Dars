"""A heartbeat and bounded metrics for the actual application event loop."""

import asyncio
import json
import logging
from pathlib import Path
from time import monotonic, time

from app.core.metrics import snapshot
from app.db.session import engine

HEARTBEAT = Path("/tmp/godofdars-heartbeat")
logger = logging.getLogger(__name__)


async def monitor_runtime() -> None:
    last_log = monotonic()
    while True:
        HEARTBEAT.write_text(str(time()))
        started = monotonic()
        await asyncio.sleep(5)
        lag = max(0.0, monotonic() - started - 5)
        if monotonic() - last_log >= 60:
            logger.info(
                "capacity loop_lag_ms=%.1f pool=%s metrics=%s",
                lag * 1000,
                engine.pool.status(),
                json.dumps(snapshot()),
            )
            last_log = monotonic()
