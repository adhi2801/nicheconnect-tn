"""The calendar file's format rules (RFC 5545), proven for every input (item 69)."""

from datetime import UTC, date, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import IST
from app.modules.deal_memo.calendar_ics import Event, calendar, escape, fold

STAMP = datetime(2026, 10, 14, 9, 30, tzinfo=UTC)
# RFC 5545 section 3.1, written here rather than read from the module, so a
# change to the module's limit cannot quietly change what is tested.
RFC_LINE_OCTETS = 75


def unescape(value: str) -> str:
    out, chars = [], iter(value)
    for char in chars:
        if char == "\\":
            following = next(chars)
            out.append("\n" if following == "n" else following)
        else:
            out.append(char)
    return "".join(out)


def unfold(text: str) -> list[str]:
    return text.replace("\r\n ", "").split("\r\n")


@given(st.text())
def test_text_can_never_break_out_of_its_field(value):
    """A title written by a person cannot end an event or start a property."""
    escaped = escape(value)

    assert "\r" not in escaped and "\n" not in escaped
    assert unescape(escaped) == value.replace("\r\n", "\n").replace("\r", "\n")


@given(st.text(min_size=1, max_size=400))
def test_every_folded_line_fits_and_unfolds_to_the_original(value):
    pieces = fold("SUMMARY:" + value)

    assert all(len(piece.encode("utf-8")) <= RFC_LINE_OCTETS for piece in pieces)
    assert all(piece.startswith(" ") for piece in pieces[1:])
    assert pieces[0] + "".join(piece[1:] for piece in pieces[1:]) == "SUMMARY:" + value


def test_a_tamil_title_folds_between_characters_not_inside_one():
    pieces = fold("SUMMARY:" + "பொங்கல் இனிப்பு " * 10)

    for piece in pieces:
        piece.encode("utf-8").decode("utf-8")  # each line is whole UTF-8
        assert len(piece.encode("utf-8")) <= RFC_LINE_OCTETS


def test_a_whole_file_follows_the_rules():
    text = calendar(
        "Deal: Pongal, sweets; launch",
        [
            Event(
                "a@x", "Content due", "Agreed.", date(2026, 12, 31), timedelta(hours=24)
            ),
            Event("b@x", "Approves itself", "Unless.", datetime(2026, 10, 9, tzinfo=IST)),
        ],
        stamp=STAMP,
    )
    lines = unfold(text)

    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    assert lines[:5] == [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NicheConnect TN//Deal dates//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    assert "X-WR-CALNAME:Deal: Pongal\\, sweets\\; launch" in lines
    # All day: a DATE start and the next day as the end.
    assert "DTSTART;VALUE=DATE:20261231" in lines
    assert "DTEND;VALUE=DATE:20270101" in lines
    # A moment in UTC: midnight in Tamil Nadu is 18:30 the evening before.
    assert "DTSTART:20261008T183000Z" in lines
    assert lines.count("DTSTAMP:20261014T093000Z") == 2
    assert lines.count("BEGIN:VALARM") == 1 and "TRIGGER:-PT24H" in lines
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == 2
    assert lines[-2] == "END:VCALENDAR"


def test_an_empty_calendar_is_still_a_valid_file():
    lines = unfold(calendar("Deal: x", [], stamp=STAMP))

    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"
    assert "BEGIN:VEVENT" not in lines
