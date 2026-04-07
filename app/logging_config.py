from __future__ import annotations

import logging

from app.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def initialize_logging(level: str | None = None) -> None:
    resolved_level = (level or settings.log_level).upper()

    logging.basicConfig(
        level=resolved_level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        force=True,
    )

