"""What every change to part of a row checks before it reaches the database.

A change schema makes each field optional, so a field left out stays as it
is. Null is then valid for every field too, and for a column that always
holds a value it reached the database as a NOT NULL violation, answered 500
(the deal memo's independent review, 27 October 2026; audit C6, 7 November).
`tests/test_update_schemas.py` holds every change schema to its table.
"""

from collections.abc import Iterable

from pydantic import BaseModel
from pydantic_core import PydanticCustomError


def check_change(change: BaseModel, always_set: Iterable[str]) -> None:
    """Refuse an empty change, and null for any field in `always_set`."""
    if not change.model_fields_set:
        raise PydanticCustomError("empty_update", "Send at least one field to change")
    for name in always_set:
        if name in change.model_fields_set and getattr(change, name) is None:
            raise PydanticCustomError(
                "value_required", "{field} cannot be null", {"field": name}
            )
