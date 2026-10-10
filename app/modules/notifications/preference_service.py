"""Notification preferences, and the one rule that applies them (D-079).

`decide` is what the push and WhatsApp sender will ask before sending
anything: send now, hold until quiet hours end, save for the daily digest,
or keep it in the app only. It is written and tested now, before any sender
exists, so the sender is built around it rather than having it bolted on.

The order of the rule matters, and each step has a reason:

1. **Urgent always goes now.** A deadline is running against the reader;
   holding it would cost them time they cannot get back.
2. **Muted stays in the app.** The person said so. It is still in their list.
3. **Daily digest** collects everything else for one moment a day.
4. **Quiet hours** hold what is left until they end.

The defaults (D-079): quiet hours 22:00 to 08:00 Tamil Nadu time, digest
off, nothing muted. Only non-urgent notifications ever wait, and those can
wait until morning; night-time pings are the top reason people uninstall
(D-071).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import IST
from app.core.export import ExportedSection, allow, build_section
from app.modules.notifications.exceptions import UrgentTypeNotMutable
from app.modules.notifications.preference_models import (
    URGENT_TYPES,
    NotificationPreference,
)

DEFAULT_QUIET_FROM = time(22, 0)
DEFAULT_QUIET_UNTIL = time(8, 0)
DEFAULT_DIGEST = "off"
DEFAULT_DIGEST_HOUR = 19

EXPORTED_TABLES = frozenset({"notification_preference"})
EXPORT_FIELDS = allow(
    "quiet_from", "quiet_until", "digest", "digest_hour", "muted_types", "updated_at"
)


@dataclass(frozen=True)
class Preferences:
    quiet_from: time | None
    quiet_until: time | None
    digest: str
    digest_hour: int
    muted_types: tuple[str, ...]
    # When the person last saved; None while they are on the defaults.
    saved_at: datetime | None


DEFAULTS = Preferences(
    quiet_from=DEFAULT_QUIET_FROM,
    quiet_until=DEFAULT_QUIET_UNTIL,
    digest=DEFAULT_DIGEST,
    digest_hour=DEFAULT_DIGEST_HOUR,
    muted_types=(),
    saved_at=None,
)


def _from_row(row: NotificationPreference) -> Preferences:
    return Preferences(
        quiet_from=row.quiet_from,
        quiet_until=row.quiet_until,
        digest=row.digest,
        digest_hour=row.digest_hour,
        muted_types=tuple(row.muted_types),
        saved_at=row.updated_at,
    )


def get(db: Session, account_id: uuid.UUID) -> Preferences:
    """This account's preferences, or the defaults if it never saved any."""
    row = db.scalars(
        select(NotificationPreference).where(
            NotificationPreference.account_id == account_id
        )
    ).first()
    return DEFAULTS if row is None else _from_row(row)


def save(
    db: Session,
    account_id: uuid.UUID,
    *,
    quiet_from: time | None,
    quiet_until: time | None,
    digest: str,
    digest_hour: int,
    muted_types: list[str],
    now: datetime,
) -> Preferences:
    """Replace this account's preferences with exactly these.

    One statement that inserts or updates, so two saves at once never fail:
    the last one wins whole, never a mix of the two.
    Raises UrgentTypeNotMutable before writing anything.
    """
    urgent = sorted(set(muted_types) & set(URGENT_TYPES))
    if urgent:
        raise UrgentTypeNotMutable(
            f"These always arrive at once, because a deadline runs against you: "
            f"{', '.join(urgent)}."
        )
    values = {
        "quiet_from": quiet_from,
        "quiet_until": quiet_until,
        "digest": digest,
        "digest_hour": digest_hour,
        "muted_types": sorted(set(muted_types)),
        "updated_at": now,
    }
    db.execute(
        insert(NotificationPreference)
        .values(account_id=account_id, created_at=now, **values)
        .on_conflict_do_update(index_elements=["account_id"], set_=values)
    )
    db.commit()
    return get(db, account_id)


# --- applying them ---------------------------------------------------------------------------

NOW = "now"
HELD = "held"
DIGEST = "digest"
IN_APP_ONLY = "in_app_only"


@dataclass(frozen=True)
class Delivery:
    how: str
    # When to send, for HELD and DIGEST; None otherwise.
    send_at: datetime | None = None


def _next(moment: datetime, at: time) -> datetime:
    """The next time the clock in Tamil Nadu reads `at`, strictly after `moment`."""
    local = moment.astimezone(IST)
    candidate = datetime.combine(local.date(), at, tzinfo=IST)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def in_quiet_hours(prefs: Preferences, moment: datetime) -> bool:
    if prefs.quiet_from is None or prefs.quiet_until is None:
        return False
    now = moment.astimezone(IST).time()
    start, end = prefs.quiet_from, prefs.quiet_until
    if start < end:  # e.g. 13:00 to 15:00
        return start <= now < end
    return now >= start or now < end  # across midnight, e.g. 22:00 to 08:00


def decide(prefs: Preferences, notification_type: str, now: datetime) -> Delivery:
    """How a notification of this type should reach this person, as of `now`."""
    if notification_type in URGENT_TYPES:
        return Delivery(NOW)
    if notification_type in prefs.muted_types:
        return Delivery(IN_APP_ONLY)
    if prefs.digest == "daily":
        return Delivery(DIGEST, _next(now, time(prefs.digest_hour)))
    if prefs.quiet_until is not None and in_quiet_hours(prefs, now):
        return Delivery(HELD, _next(now, prefs.quiet_until))
    return Delivery(NOW)


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """This account's saved preferences, if it saved any."""
    rows = list(
        db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.account_id == account_id
            )
        ).all()
    )
    return [
        build_section(
            "notification_preferences",
            table="notification_preference",
            purpose=(
                "How you asked to be told things outside the app: quiet hours, "
                "a daily digest, and what you muted. Empty if you kept the "
                "defaults."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
