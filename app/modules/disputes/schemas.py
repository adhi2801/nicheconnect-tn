"""Request and response shapes for disputes."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.literals import ensure_same_values
from app.modules.disputes.event_models import (
    EVENT_KINDS,
    NOTE_MAX_LENGTH,
    URL_MAX_LENGTH,
    DisputeEvent,
)
from app.modules.disputes.models import (
    DISPUTE_OUTCOMES,
    DISPUTE_PARTIES,
    REASON_MAX_LENGTH,
    REASON_MIN_LENGTH,
    Dispute,
)
from app.modules.disputes.service import DISPUTE_STATES

DisputeParty = Literal["brand", "creator"]
DisputeOutcome = Literal["resolved_paid", "resolved_withdrawn", "resolved_informally"]
DisputeState = Literal[
    "open", "unresolved", "resolved_paid", "resolved_withdrawn", "resolved_informally"
]
EventKind = Literal["opened", "response", "evidence", "closed"]

# Keeps these honest against the database's own allow-lists.
ensure_same_values("DisputeParty", DisputeParty, DISPUTE_PARTIES)
ensure_same_values("DisputeOutcome", DisputeOutcome, DISPUTE_OUTCOMES)
ensure_same_values("DisputeState", DisputeState, DISPUTE_STATES)
ensure_same_values("EventKind", EventKind, EVENT_KINDS)

Note = Annotated[
    str,
    Field(
        min_length=1,
        max_length=NOTE_MAX_LENGTH,
        description="What you want on the record, in your own words",
    ),
]
EvidenceUrl = Annotated[
    str,
    Field(
        pattern=r"^https://.+",
        max_length=URL_MAX_LENGTH,
        description="A link to something that supports your account",
        examples=["https://example.com/upi-receipt.png"],
    ),
]


class DisputeOpen(BaseModel):
    """Raising one. Either side may."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: Annotated[
        str,
        Field(
            min_length=REASON_MIN_LENGTH,
            max_length=REASON_MAX_LENGTH,
            description="What happened, in your own words. This opens the record.",
            examples=[
                "The payment was marked sent on 8 September but nothing has "
                "reached my account and the reference does not match."
            ],
        ),
    ]


class DisputeEntryCreate(BaseModel):
    """Adding to the record. A note, a link, or both — but not nothing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: Note | None = None
    evidence_url: EvidenceUrl | None = None


class DisputeClose(BaseModel):
    """How it ended. None of these say who was right."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    outcome: DisputeOutcome
    note: Note | None = None


class DisputeEventRead(BaseModel):
    id: uuid.UUID
    actor_role: DisputeParty
    kind: EventKind
    note: str | None
    evidence_url: str | None
    created_at: datetime


class DisputeRead(BaseModel):
    """A dispute and its timeline.

    `state` is worked out from the dates: `unresolved` means thirty days
    passed with nothing agreed. It is a fact about the dispute, never a
    finding about either person.
    """

    id: uuid.UUID
    payment_status_id: uuid.UUID
    opened_by: DisputeParty
    state: DisputeState
    response_due_on: date
    outcome: DisputeOutcome | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    timeline: list[DisputeEventRead]


def to_event_read(event: DisputeEvent) -> DisputeEventRead:
    return DisputeEventRead(
        id=event.id,
        actor_role=event.actor_role,
        kind=event.kind,
        note=event.note,
        evidence_url=event.evidence_url,
        created_at=event.created_at,
    )


def to_read(dispute: Dispute, state: str, events: list[DisputeEvent]) -> DisputeRead:
    return DisputeRead(
        id=dispute.id,
        payment_status_id=dispute.payment_status_id,
        opened_by=dispute.opened_by,
        state=state,
        response_due_on=dispute.response_due_on,
        outcome=dispute.outcome,
        closed_at=dispute.closed_at,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
        timeline=[to_event_read(event) for event in events],
    )
