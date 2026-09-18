"""One pagination style for every list endpoint (backend.md section 2).

Cursor (keyset) paging, newest first: the cursor carries the last row's
created_at and id, so pages stay correct while rows are being added.
"""

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.errors import DomainError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_SEPARATOR = "|"

Item = TypeVar("Item")


class InvalidCursor(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "invalid_cursor"
    title = "That page link is not valid. Start from the first page"


@dataclass(frozen=True)
class Slice(Generic[Item]):
    """What a service returns: database rows plus the cursor for the next page."""

    rows: list[Item]
    next_cursor: str | None


class Page(BaseModel, Generic[Item]):
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


def build_slice(rows: list[Item], limit: int, *, key) -> Slice[Item]:
    """Turn `limit + 1` fetched rows into one page and its next cursor.

    `key` takes a row and returns (created_at, id).
    """
    has_more = len(rows) > limit
    kept = rows[:limit]
    next_cursor = encode_cursor(*key(kept[-1])) if has_more and kept else None
    return Slice(rows=kept, next_cursor=next_cursor)
