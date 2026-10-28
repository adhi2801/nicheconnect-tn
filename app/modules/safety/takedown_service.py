"""A person's own takedowns: what of theirs is withheld, and why (item 52, D-104).

The owner is told when something of theirs is withheld (a `content_withheld`
notification) and can always read the list here, as X and GitHub tell the
person whose content they withhold. Who issued the order, its number and the
law it cites are shown, unless the order is sealed: then only that it exists.
The admins' names and notes, and when the order reached us, are never shown.

Placing and lifting takedowns is the admins' (admin/takedown_service.py).
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.models.account import Account
from app.modules.safety.takedown_models import Takedown

EXPORTED_TABLES = frozenset({"takedown"})
# `preserved` is the owner's own text as it stood when withheld: theirs to see.
EXPORT_FIELDS = allow(
    "id",
    "subject_kind",
    "subject_id",
    "basis",
    "reference_sealed",
    "withheld_at",
    "lifted_at",
    "preserved",
)


def order_details(takedown: Takedown) -> dict[str, Any]:
    """Who issued it, its number and its law, or nulls when it is sealed."""
    shown = not takedown.reference_sealed
    return {
        "issued_by": takedown.issued_by if shown else None,
        "order_reference": takedown.order_reference if shown else None,
        "legal_provision": takedown.legal_provision if shown else None,
    }


def list_mine(
    db: Session, owner: Account, *, limit: int, cursor: str | None
) -> Slice[Takedown]:
    """This person's takedowns, newest first, lifted ones included.

    Served by ix_takedown_owner_account_id_created_at.
    """
    query = select(Takedown).where(Takedown.owner_account_id == owner.id)
    if cursor is not None:
        query = query.where(older_than_cursor(Takedown.created_at, Takedown.id, cursor))
    rows = list(
        db.scalars(
            query.order_by(Takedown.created_at.desc(), Takedown.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda t: (t.created_at, t.id))


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """This person's takedowns, with the order's details unless it is sealed."""
    rows = list(
        db.scalars(
            select(Takedown)
            .where(Takedown.owner_account_id == account_id)
            .order_by(Takedown.created_at, Takedown.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    return [
        build_section(
            "takedowns",
            table="takedown",
            purpose=(
                "Your profile, brand or campaigns we withheld for legal reasons: "
                "on a court order or government notice under the IT Rules, or "
                "on a report while we looked into it. The law asks us to keep "
                "what was withheld, so `preserved` is your text as it stood "
                "then. A sealed order's details are not included."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
            extra=order_details,
        )
    ]
