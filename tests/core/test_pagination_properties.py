"""Cursors, for any input (D-090; testing.md section 6).

A cursor arrives from the outside world. Whatever it holds, reading it gives
the row it was made from or a clean InvalidCursor (422), never a 500.
"""

import base64
import contextlib
import uuid
from datetime import UTC, datetime, timedelta, timezone

from hypothesis import given
from hypothesis import strategies as st

from app.core.pagination import InvalidCursor, decode_cursor, encode_cursor

URL_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

# Hypothesis takes naive bounds and attaches each zone itself.
aware_times = st.datetimes(
    min_value=datetime(2000, 1, 1),  # noqa: DTZ001
    max_value=datetime(2100, 1, 1),  # noqa: DTZ001
    timezones=st.sampled_from(
        [UTC, timezone(timedelta(hours=5, minutes=30)), timezone(timedelta(hours=-7))]
    ),
)


@given(created_at=aware_times, row_id=st.uuids())
def test_a_cursor_reads_back_as_the_row_it_was_made_from(created_at, row_id):
    assert decode_cursor(encode_cursor(created_at, row_id)) == (created_at, row_id)


@given(created_at=aware_times, row_id=st.uuids())
def test_a_cursor_is_url_safe_with_no_padding(created_at, row_id):
    assert set(encode_cursor(created_at, row_id)) <= URL_SAFE


@given(st.text(max_size=200))
def test_any_text_is_read_or_refused_cleanly(cursor):
    try:
        created_at, row_id = decode_cursor(cursor)
    except InvalidCursor:
        return
    assert isinstance(created_at, datetime)
    assert isinstance(row_id, uuid.UUID)


@given(st.binary(max_size=120))
def test_any_bytes_behind_the_base64_are_read_or_refused_cleanly(raw):
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with contextlib.suppress(InvalidCursor):
        decode_cursor(cursor)
