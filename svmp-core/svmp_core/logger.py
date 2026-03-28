"""Shared logging bootstrap for SVMP."""

from __future__ import annotations

import logging
from functools import lru_cache

import structlog

from svmp_core.config import get_settings


def _resolve_log_level(level_name: str) -> int:
    """Translate a configured log level name to a stdlib logging level."""

    return getattr(logging, level_name.upper(), logging.INFO)


@lru_cache(maxsize=1)
def configure_logging() -> None:
    """Configure structlog once for the application process."""

    settings = get_settings()
    log_level = _resolve_log_level(settings.LOG_LEVEL)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Return an app-scoped structured logger."""

    settings = get_settings()
    configure_logging()
    return structlog.get_logger(name).bind(app=settings.APP_NAME, env=settings.APP_ENV)
