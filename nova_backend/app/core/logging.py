"""Logging configuration.

Previously this used `logging.basicConfig` with a plain format string, which
meant every `logger.info(..., extra={...})` call in the codebase silently threw
its structured fields away — they were never rendered. Anything you actually
wanted to search on was lost.

Now: JSON lines in deployed environments (greppable, ingestible), human-readable
text locally, and the request context attached to every record automatically.
"""

import json
import logging
import sys
from typing import Any

from app.core.config import get_settings
from app.core.context import current_context

#: Attributes present on every LogRecord. Anything else was passed via `extra`
#: and is therefore application data worth emitting.
_STANDARD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(current_context())
        payload.update(_extra_fields(record))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Readable local output that still shows the structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} "
            f"{record.name} {record.getMessage()}"
        )
        fields = {**current_context(), **_extra_fields(record)}
        if fields:
            base += "  " + " ".join(f"{k}={v}" for k, v in fields.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    settings = get_settings()
    level = logging.DEBUG if settings.debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(HumanFormatter() if settings.env == "local" else JsonFormatter())

    root = logging.getLogger()
    # Replace rather than append, so repeated calls (tests, reload) do not
    # duplicate every log line.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # SQLAlchemy echoes every statement at INFO; far too noisy outside debugging.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
