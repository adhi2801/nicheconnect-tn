"""A calendar file (iCalendar, RFC 5545), written by hand (item 69, D-102).

The format is plain text with a few exact rules, so no package is needed:

- lines end in CRLF (section 3.1);
- a line longer than 75 octets is folded: a CRLF and one space, never
  splitting a UTF-8 character (section 3.1);
- in text values a backslash, semicolon, comma and newline are escaped
  (section 3.3.11), so text written by a person, such as a campaign title,
  can never end an event or start a new property;
- an all-day event is a DATE start and the next day as its end (section
  3.6.1); a moment is written in UTC with a Z (section 3.3.5), so every
  calendar shows it in its own time zone without a VTIMEZONE block;
- every event has a UID that never changes, so adding the file again
  updates the events instead of copying them (section 3.8.4.7), and a
  DTSTAMP (section 3.8.7.2).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

PRODID = "-//NicheConnect TN//Deal dates//EN"
LINE_OCTETS = 75


@dataclass(frozen=True)
class Event:
    uid: str
    summary: str
    description: str
    # A date is an all-day event; a datetime is a moment.
    start: date | datetime
    # Remind this long before the start; None for no reminder.
    remind_before: timedelta | None = None


def escape(value: str) -> str:
    """Text as RFC 5545 section 3.3.11 writes it."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> list[str]:
    """One logical line as physical lines of at most 75 octets (section 3.1).

    A continuation line starts with a space, which counts toward its 75.
    Splits fall only between characters, so UTF-8 stays whole.
    """
    pieces: list[str] = []
    current, size, limit = "", 0, LINE_OCTETS
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            pieces.append(current)
            current, size, limit = "", 0, LINE_OCTETS - 1
        current += char
        size += width
    pieces.append(current)
    return [pieces[0], *(" " + piece for piece in pieces[1:])]


def _moment(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _day(value: date) -> str:
    return value.strftime("%Y%m%d")


def _event_lines(event: Event, stamp: datetime) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{event.uid}", f"DTSTAMP:{_moment(stamp)}"]
    if isinstance(event.start, datetime):
        lines.append(f"DTSTART:{_moment(event.start)}")
    else:
        lines.append(f"DTSTART;VALUE=DATE:{_day(event.start)}")
        lines.append(f"DTEND;VALUE=DATE:{_day(event.start + timedelta(days=1))}")
    lines.append(f"SUMMARY:{escape(event.summary)}")
    lines.append(f"DESCRIPTION:{escape(event.description)}")
    lines.append("TRANSP:TRANSPARENT")  # a deadline, not a meeting: not busy
    if event.remind_before is not None:
        hours = int(event.remind_before.total_seconds() // 3600)
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"TRIGGER:-PT{hours}H",
            f"DESCRIPTION:{escape(event.summary)}",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def calendar(name: str, events: Sequence[Event], *, stamp: datetime) -> str:
    """The whole file, CRLF line ends, every line folded."""
    logical = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
    ]
    for event in events:
        logical += _event_lines(event, stamp)
    logical.append("END:VCALENDAR")
    return "".join(physical + "\r\n" for line in logical for physical in fold(line))
