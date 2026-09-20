"""Shared pieces for building a person's data export.

An export is the most PII-dense thing this API will ever produce, so the
rules are enforced here rather than trusted to each caller:

- **Fields are declared, never discovered.** A section lists the columns it
  releases. A column added to a table later does not appear in an export
  until somebody adds it here on purpose — the same discipline the public
  Creator Passport uses.
- **Some names can never be declared at all.** `allow()` refuses anything
  that looks like a secret, and it refuses at import time, so a mistake
  stops the app from starting instead of leaking on a live request.
- **Nothing is unbounded.** A section carries at most `MAX_ROWS_PER_SECTION`
  rows and says so when it had more, because an export that quietly drops
  data is worse than one that admits it.
- **Unknown types are an error.** A new column type has to be thought about,
  not silently turned into a string.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

# Enough for any pilot account, small enough that one request cannot exhaust
# memory. A section that hits it reports `truncated`.
MAX_ROWS_PER_SECTION = 5_000

# No field whose name contains one of these may ever be exported. Checked
# when a section declares its fields, which happens at import.
NEVER_EXPORTED = frozenset({"hash", "token", "secret", "password"})


class ForbiddenExportField(ValueError):
    """Raised at import time when a section declares an unsafe field."""


def allow(*names: str) -> tuple[str, ...]:
    """Declare the fields of a table that may leave the building.

    Raises immediately if a name looks like a secret, so the mistake is a
    failed start-up rather than a leak.
    """
    for name in names:
        lowered = name.lower()
        for banned in NEVER_EXPORTED:
            if banned in lowered:
                raise ForbiddenExportField(
                    f"'{name}' cannot be exported: names containing "
                    f"'{banned}' are never released"
                )
    return names


def to_json_value(value: Any) -> Any:
    """Turn a database value into something JSON can carry.

    Timestamps come back as ISO 8601 in UTC ending in `Z`, matching every
    other date this API returns (backend.md section 2).
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        # Columns are TIMESTAMPTZ, so this is normally already aware. A naive
        # value is read as UTC rather than as the server's local time, which
        # would silently shift every timestamp in the file.
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    raise TypeError(
        f"{type(value).__name__} has no agreed export form; decide on one "
        f"here rather than letting it be stringified"
    )


def export_row(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """One row, reduced to its declared fields."""
    return {name: to_json_value(getattr(obj, name)) for name in fields}


@dataclass(frozen=True)
class ExportedSection:
    """One part of an export, and the record of where it came from."""

    name: str
    # The database table this section reports on. The completeness test
    # reads these, so no table can be quietly left out of an export.
    table: str
    # Why we hold this data, in words the person reading the file will
    # understand (security.md section 6: every PII field has a purpose).
    purpose: str
    records: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def manifest_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "section": self.name,
            "records": len(self.records),
            "purpose": self.purpose,
        }
        if self.truncated:
            entry["truncated"] = True
            entry["note"] = (
                f"Only the first {MAX_ROWS_PER_SECTION:,} records are included. "
                f"Ask us for the rest."
            )
        return entry


def build_section(
    name: str,
    *,
    table: str,
    purpose: str,
    objects: list[Any],
    fields: tuple[str, ...],
    extra: Callable[[Any], dict[str, Any]] | None = None,
) -> ExportedSection:
    """Serialise rows into a section, trimming to the cap if there are more.

    Callers query with `MAX_ROWS_PER_SECTION + 1` so that going over the cap
    is visible here rather than guessed at.

    `extra` adds fields that are not columns on the row — a campaign's title
    beside an application, for instance, so the file reads as a record of
    what happened rather than a list of identifiers. Its keys go through the
    same check as declared fields, and it must never be used to smuggle in
    another person's private details.
    """
    truncated = len(objects) > MAX_ROWS_PER_SECTION
    kept = objects[:MAX_ROWS_PER_SECTION]

    records: list[dict[str, Any]] = []
    for obj in kept:
        record = export_row(obj, fields)
        if extra is not None:
            added = extra(obj)
            allow(*added)
            record |= {key: to_json_value(item) for key, item in added.items()}
        records.append(record)

    return ExportedSection(
        name=name,
        table=table,
        purpose=purpose,
        records=records,
        truncated=truncated,
    )
