"""structlog, JSON output. No print() outside scripts/.

Our own logs and stdlib logs (uvicorn, sqlalchemy, alembic, litellm) are rendered by the same
JSON processor, so stdout stays one parseable stream instead of two interleaved formats.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False

# Applied to events from structlog and from stdlib logging alike.
_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.EventRenamer("message"),
]


def configure_logging(level: str | None = None) -> None:
    """Configure structlog + stdlib for JSON output.

    Idempotent — every entrypoint (API lifespan, CLI scripts) calls it without coordinating.
    """
    global _configured
    if _configured:
        return

    from app.core.config import get_settings

    log_level = (level or get_settings().log_level).upper()

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            # Hands the event dict to ProcessorFormatter instead of rendering it here.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            # foreign_pre_chain handles records from libraries that never touched structlog.
            foreign_pre_chain=_SHARED_PROCESSORS,
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # uvicorn installs its own handlers before our lifespan runs; without this its output
    # bypasses the JSON formatter entirely.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = []
        stdlib_logger.propagate = True

    _configured = True


def get_logger(name: str | None = None, **initial: Any) -> structlog.stdlib.BoundLogger:
    """Get a bound logger. Call configure_logging() once at the entrypoint first."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger.bind(**initial) if initial else logger
