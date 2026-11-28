"""Cursors and pages, by fixed example (backend.md section 2; testing.md section 2).

The properties in `test_pagination_properties.py` say what holds for any
cursor; these pin the page's edges exactly, so a slip at the boundary (one
row too many, a cursor on the last page) fails on every run rather than only
when Hypothesis happens to generate exactly `limit` rows.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, Tuple

from app.core.pagination import (
    build_slice,
    decode_cursor,
    encode_cursor,
    older_than_cursor,
)

START = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)


class _Base(DeclarativeBase):
    """A metadata of the test's own: nothing here reaches the app's schema."""


class Row(_Base):
    __tablename__ = "paged_row"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def rows(count: int) -> list[tuple[datetime, uuid.UUID]]:
    """`count` rows, newest first, as a list query returns them."""
    return [(START - timedelta(minutes=i), uuid.uuid4()) for i in range(count)]


def page(fetched: list[tuple[datetime, uuid.UUID]], limit: int):
    return build_slice(fetched, limit, key=lambda row: row)


# --- one page from `limit + 1` fetched rows ------------------------------------------


def test_exactly_limit_rows_is_the_last_page():
    fetched = rows(3)

    result = page(fetched, 3)

    assert result.rows == fetched
    assert result.next_cursor is None


def test_one_row_past_the_limit_gives_a_cursor_naming_the_last_row_kept():
    fetched = rows(4)

    result = page(fetched, 3)

    assert result.rows == fetched[:3]
    assert result.next_cursor is not None
    assert decode_cursor(result.next_cursor) == fetched[2]


def test_fewer_rows_than_the_limit_is_the_last_page():
    fetched = rows(1)

    result = page(fetched, 3)

    assert result.rows == fetched
    assert result.next_cursor is None


def test_no_rows_is_an_empty_last_page():
    result = page([], 3)

    assert result.rows == []
    assert result.next_cursor is None


def test_a_limit_of_zero_keeps_nothing_and_names_no_row():
    """Rows past a zero limit: nothing kept, so there is no last row to name.
    The API refuses a zero limit; the guard keeps a caller that does not from
    an IndexError (a 500)."""
    result = page(rows(2), 0)

    assert result.rows == []
    assert result.next_cursor is None


# --- the next page's condition ---------------------------------------------------------


def cursor_condition() -> tuple[BinaryExpression[bool], ...]:
    cursor_time, cursor_id = START, uuid.UUID(int=7)
    condition = older_than_cursor(
        Row.created_at, Row.id, encode_cursor(cursor_time, cursor_id)
    )
    return tuple(condition.clauses)


def test_the_condition_is_a_plain_range_and_a_row_value_comparison():
    """The index contract (database.md sections 5 and 7). The row-value
    comparison `(created_at, id) < (time, id)` decides which rows come next;
    the plain `created_at <= time` beside it is logically redundant and is
    there for the planner, which uses a simple range on the `(...,
    created_at)` indexes every list reads. Dropping it changes no result,
    only the plan, so this test, not a result, is what keeps it."""
    range_term, row_value_term = cursor_condition()

    assert range_term.left.compare(Row.__table__.c.created_at)
    assert range_term.operator is operators.le
    assert isinstance(range_term.right, BindParameter)
    assert range_term.right.value == START

    assert row_value_term.operator is operators.lt
    assert isinstance(row_value_term.left, Tuple)
    created_at, row_id = row_value_term.left.clauses
    assert created_at.compare(Row.__table__.c.created_at)
    assert row_id.compare(Row.__table__.c.id)
    assert isinstance(row_value_term.right, Tuple)
    assert [bind.value for bind in row_value_term.right.clauses] == [
        START,
        uuid.UUID(int=7),
    ]


def test_the_condition_reaches_postgres_as_both_terms():
    """The same contract, read as the SQL PostgreSQL is sent."""
    condition = older_than_cursor(
        Row.created_at, Row.id, encode_cursor(START, uuid.UUID(int=7))
    )

    sql = str(condition.compile(dialect=postgresql.dialect()))

    assert sql.startswith("paged_row.created_at <= %(created_at_1)s")
    assert " AND (paged_row.created_at, paged_row.id) < (" in sql
