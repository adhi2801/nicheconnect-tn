"""No change may send null for a column that always holds a value (audit C6).

Each `*Update` schema makes every field optional, so a change can leave a
field out; but `{"title": null}` is also a valid body for an optional field,
and it reached the database as a NOT NULL violation: a 500, not a 422. The
independent review of item 27 found it in the deal memo (27 October 2026);
audit C6 (7 November) found the same in campaigns, profiles and rate-card
packages. This compares every change schema with its table, so a new field
or a new schema cannot bring it back.
"""

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import DeclarativeBase

from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
from app.modules.campaigns.schemas import CampaignUpdate
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.schemas import MemoUpdate
from app.modules.profiles.models import CreatorPackage
from app.modules.profiles.schemas import (
    BrandProfileUpdate,
    CreatorProfileUpdate,
    PackageUpdate,
)

# Every schema that changes part of a row, with the row's table.
CHANGES: list[tuple[type[BaseModel], type[DeclarativeBase]]] = [
    (BrandProfileUpdate, Brand),
    (CreatorProfileUpdate, Creator),
    (PackageUpdate, CreatorPackage),
    (CampaignUpdate, Campaign),
    (MemoUpdate, DealMemo),
]


def _cases() -> list[tuple[type[BaseModel], str, bool]]:
    cases = []
    for schema, table in CHANGES:
        columns = table.__table__.columns  # type: ignore[attr-defined]
        for name in schema.model_fields:
            if name in columns:
                cases.append((schema, name, columns[name].nullable))
    return cases


def test_every_schema_that_changes_part_of_a_row_is_listed():
    """A new `*Update` schema must join CHANGES, or this fails."""
    from app.main import app  # noqa: F401 - imports every module's schemas

    def every_subclass(cls: type) -> list[type]:
        return [s for c in cls.__subclasses__() for s in (c, *every_subclass(c))]

    updates = {
        s
        for s in every_subclass(BaseModel)
        if s.__name__.endswith("Update") and s.__module__.startswith("app.")
    }
    listed = {schema for schema, _ in CHANGES}
    # Not a row's columns: the creator's own availability date, cleared by null.
    exempt = {"AvailabilityUpdate"}

    assert {s.__name__ for s in updates - listed} == exempt


@pytest.mark.parametrize(
    ("schema", "field", "nullable"),
    _cases(),
    ids=lambda v: v.__name__ if isinstance(v, type) else str(v),
)
def test_null_is_refused_where_the_column_always_holds_a_value(schema, field, nullable):
    if nullable:
        schema.model_validate({field: None})
        return
    with pytest.raises(ValidationError) as refused:
        schema.model_validate({field: None})
    assert refused.value.errors()[0]["type"] == "value_required"
