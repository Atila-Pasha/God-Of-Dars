from __future__ import annotations

import logging


def configure_logging(environment: str) -> None:
    """Configure useful process-wide logs without replacing host handlers."""
    level = logging.DEBUG if environment.casefold() == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
