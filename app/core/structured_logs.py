"""Logs as one JSON object per line, with no personal data (D-102).

backend.md section 9: "log events, not data". In production, CloudWatch can
search and alert on fields only when each line is JSON; until now the app
wrote plain text. On when `LOG_FORMAT=json` (infra sets it); a laptop keeps
readable lines.

Each line carries the time in UTC, the level, the logger, the event, the
request's id and, when tracing is on, its trace id, so a line leads to its
trace (D-094). Three nets keep personal data out, on top of the rule that no
log call writes any:

- the event text passes through the same redaction as error reports
  (`error_tracking.redact`: phone numbers, emails, UPI IDs, long numbers);
- an exception logs its type and its stack frames, never its message,
  which can quote a database row and the person in it;
- Uvicorn's access line is rebuilt from its method, path and status: the
  client's address and the query string (which can hold search words or a
  handle) never reach a log.
"""

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from app.core.error_tracking import redact
from app.core.request_id import request_id_var

ACCESS_LOGGER = "uvicorn.access"
# Loggers Uvicorn configures with handlers of its own; they are sent through
# the one JSON handler instead, so every line has the same shape.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", ACCESS_LOGGER)


def _event(record: logging.LogRecord) -> str:
    if (
        record.name == ACCESS_LOGGER
        and isinstance(record.args, tuple)
        and len(record.args) == 5
    ):
        # Uvicorn passes (client, method, path, http version, status).
        _, method, path, _, status = record.args
        return f"http.request method={method} path={str(path).split('?', 1)[0]} status={status}"
    return str(redact(record.getMessage()))


def _exception(record: logging.LogRecord) -> dict[str, Any] | None:
    if not record.exc_info or record.exc_info[0] is None:
        return None
    kind, _, tb = record.exc_info
    return {
        "type": kind.__name__,
        # Where it happened, without what it said. The frames quote source
        # lines, so they are redacted too (a test's line quoted a number).
        "stack": str(redact("".join(traceback.format_tb(tb)).rstrip())),
    }


def _trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


class JsonFormatter(logging.Formatter):
    """One JSON object per line, no personal data."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": _event(record),
            "request_id": request_id_var.get(),
            "trace_id": _trace_id(),
        }
        exception = _exception(record)
        if exception is not None:
            line["exception"] = exception
        return json.dumps(line, ensure_ascii=False)


def configure_logging(log_format: str, level: str = "INFO") -> None:
    """In JSON mode, send every log line, Uvicorn's included, through one handler.

    In text mode, change nothing: Uvicorn's own readable lines stay.
    """
    if log_format != "json":
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
