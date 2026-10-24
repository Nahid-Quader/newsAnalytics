"""Structured (JSON) logging.

Use `log_event(logger, "event_name", key=value, ...)` so every record carries machine-readable fields.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", {})
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        base = f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        return f"{base} {extra}".rstrip()


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_output else PlainFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # httpx logs every request at INFO; our own fetch events are more useful.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})
