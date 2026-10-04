"""Error tracking: every unexpected error reaches a founder, personal data never does (D-074).

Until now an unexpected error was a log line in CloudWatch that nobody would
read until a user complained. Sentry turns it into an alert with its stack
trace, grouped with every other occurrence of the same bug, and tagged with
the release that introduced it.

What is sent: the error logs the app already writes. `logger.exception` in
the 500 handler (app/core/errors.py), and the two `logger.error` calls for a
login code that failed to send and a checkpoint that failed to anchor. Each
becomes one Sentry event. The web framework's own capture of 5xx answers is
switched off: a 503 raised on purpose (a dependency down) is a refusal, not a
bug, and what is reported stays exactly what the app logs as an error.

What is never sent, because the people in this marketplace trust us with
their phone numbers, payments and income (security.md, constraint 2):

- request bodies, cookies, query strings and the signed-in account;
- local variables in the stack trace, where a phone number or a token sits;
- the caller's IP address (Sentry's `send_default_pii` is off);
- any phone number, email, UPI ID or long number anywhere else in the event,
  such as a database error that quotes the row it refused. Those are
  replaced with a placeholder before the event leaves the process.

That last net is a pattern, so it is a safety net, not a licence: the rule
that no log line carries personal data still holds.

No performance tracing: errors only, which keeps us inside the free plan.
"""

import logging
import re
from collections.abc import Callable
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from sentry_sdk.types import Event, Hint

from app.core.config import Settings

# Replaced wherever they appear in an event, in this order. The look-behind
# and look-ahead stop a match inside an ID: a UUID's last group is twelve
# digits often enough, but it follows a hyphen, and an ID is worth keeping.
EMAIL_OR_UPI = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*")
PHONE = re.compile(r"(?<![\w-])(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?![\w-])")
# Bank account numbers, payment references, phone numbers in other formats.
LONG_NUMBER = re.compile(r"(?<![\w-])\d{9,}(?![\w-])")
REDACTIONS = ((EMAIL_OR_UPI, "[email]"), (PHONE, "[phone]"), (LONG_NUMBER, "[number]"))

# Header and field names whose values are dropped wherever they appear, on
# top of Sentry's own list (authorization, cookie, token, password, ...).
EXTRA_DENYLIST = ["phone", "otp", "code", "upi", "upi_id", "account_number", "ifsc"]

# The parts of a request event that can carry what a person typed or who
# they are. The method, the path and the scrubbed headers stay.
REQUEST_FIELDS_DROPPED = ("data", "cookies", "query_string", "env")


def redact(value: Any) -> Any:
    """`value` with every phone number, email and long number replaced."""
    if isinstance(value, str):
        for pattern, placeholder in REDACTIONS:
            value = pattern.sub(placeholder, value)
        return value
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


def scrub_event(event: Event, hint: Hint) -> Event:
    """The last step before an event leaves the process."""
    request = event.get("request")
    if isinstance(request, dict):
        for field in REQUEST_FIELDS_DROPPED:
            request.pop(field, None)
    event.pop("user", None)
    redacted: Event = redact(event)
    return redacted


def scrub_breadcrumb(crumb: dict[str, Any], hint: Hint) -> dict[str, Any]:
    """Breadcrumbs (the log lines and queries before an error) get the same net."""
    cleaned: dict[str, Any] = redact(crumb)
    return cleaned


def init_error_tracking(
    settings: Settings, *, transport: Callable[..., Any] | type | None = None
) -> bool:
    """Start sending errors to Sentry if SENTRY_DSN is set. True if it started.

    `transport` is for tests, which collect events instead of sending them.
    """
    if settings.sentry_dsn is None:
        return False
    options: dict[str, Any] = {}
    if transport is not None:
        options["transport"] = transport
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.app_release,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        event_scrubber=EventScrubber(
            denylist=DEFAULT_DENYLIST + EXTRA_DENYLIST, recursive=True
        ),
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        integrations=[
            # Crashes arrive through their log line (below). The framework's
            # own capture would add every 5xx raised on purpose, such as a
            # 503 while a dependency is down, which is not a bug.
            StarletteIntegration(failed_request_status_codes=set()),
            FastApiIntegration(failed_request_status_codes=set()),
            # Error lines become events; lower lines only travel with them as
            # breadcrumbs, already scrubbed.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        **options,
    )
    return True
