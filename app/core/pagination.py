"""One pagination style for every list endpoint (backend.md section 2).

Cursor (keyset) paging, newest first: the cursor carries the last row's
created_at and id, so pages stay correct while rows are being added.
"""

import base64
import binascii
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, and_, literal, tuple_
from sqlalchemy.orm import QueryableAttribute

from app.core.errors import DomainError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_SEPARATOR = "|"


class InvalidCursor(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "invalid_cursor"
    title = "That page link is not valid. Start from the first page"


@dataclass(frozen=True)
class Slice[Item]:
    """What a service returns: database rows plus the cursor for the next page."""

    rows: list[Item]
    next_cursor: str | None


class Page[Item](BaseModel):
    """What an endpoint returns. `next_cursor` is null on the last page."""

    items: list[Item]
    next_cursor: str | None = Field(
        default=None, description="Pass as ?cursor= to get the next page"
    )


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    """Opaque cursor for the last row of a page."""
    raw = f"{created_at.isoformat()}{_SEPARATOR}{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Read a cursor back. Raises InvalidCursor for anything malformed."""
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        created_at_text, row_id_text = raw.split(_SEPARATOR)
        return datetime.fromisoformat(created_at_text), uuid.UUID(row_id_text)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursor() from exc


def older_than_cursor(
    created_at: QueryableAttribute[datetime],
    row_id: QueryableAttribute[uuid.UUID],
    cursor: str,
) -> ColumnElement[bool]:
    """The rows that come after `cursor` in newest-first order.

    One row-value comparison, `(created_at, id) < (cursor_time, cursor_id)`,
    so rows sharing the cursor's timestamp are ordered by id, not skipped.

    Never write this as two Python tuples. Python compares tuples itself,
    element by element; SQLAlchemy's `==` between a column and a value is
    not truthy, so what reaches the database is only `created_at < time` and
    every row tied with the last one on the page disappears. That was the
    bug in all four list endpoints until 2026-09-21.

    The plain `created_at <=` is logically redundant. It is there because it
    is a simple range the planner can use on the `(..., created_at)` indexes.
    Raises InvalidCursor for anything malformed.
    """
    cursor_time, cursor_id = decode_cursor(cursor)
    return and_(
        created_at <= cursor_time,
        tuple_(created_at, row_id) < tuple_(literal(cursor_time), literal(cursor_id)),
    )


def build_slice[Item](
    rows: list[Item],
    limit: int,
    *,
    key: Callable[[Item], tuple[datetime, uuid.UUID]],
) -> Slice[Item]:
    """Turn `limit + 1` fetched rows into one page and its next cursor.

    `key` takes a row and returns (created_at, id).
    """
    has_more = len(rows) > limit
    kept = rows[:limit]
    next_cursor = encode_cursor(*key(kept[-1])) if has_more and kept else None
    return Slice(rows=kept, next_cursor=next_cursor)
