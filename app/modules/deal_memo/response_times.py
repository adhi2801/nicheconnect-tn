"""Typical response times, measured from the deal record (D-077).

"Brands usually decide on work within 2 days." Known waiting is easier than
unknown waiting (`docs/PSYCHOLOGY_AND_TRUST.md`), so each side is told how
long the other usually takes, but only from what happened: the dated,
sealed entries in each deal's record, never an estimate and never a promise.

Three are measured, each from a request to the other side's answer:

- **work reviewed** (brand): work submitted, then approved or sent back. An
  approval by the clock (D-025) counts, at the moment the window ended:
  that is how long the creator actually waited.
- **memo answered** (creator): a memo sent, then accepted, declined or
  answered with a change request. A memo the brand withdrew first was never
  answered, so it is left out rather than counted as slow.
- **payment confirmed** (creator): the brand says it sent the money, then
  the creator confirms it arrived.

A request still waiting is not counted: it has no answer yet to time.

**Five examples or nothing** (D-071). Below five, `median_hours` is null,
meaning not enough to say, and must never be shown as zero. The number of
examples is always returned, so a reader can weigh it.

Not measured: how fast a brand answers an application. Only the latest
status change is stored, not the first, so any figure would be a guess.
"""

import statistics
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import DealRecordEntry

MIN_EXAMPLES = 5  # D-071

# What starts each wait, and what ends it.
WORK_REVIEWED = (
    "proof_submitted",
    frozenset({"proof_approved", "proof_auto_approved", "proof_revision_requested"}),
)
MEMO_ANSWERED = (
    "memo_sent",
    frozenset({"memo_accepted", "memo_declined", "memo_change_requested"}),
)
PAYMENT_CONFIRMED = ("payment_marked_paid", frozenset({"payment_confirmed"}))
# Ends a wait without an answer: the request went away.
WITHDRAWN = frozenset({"memo_cancelled"})

KINDS = frozenset(
    {WORK_REVIEWED[0], MEMO_ANSWERED[0], PAYMENT_CONFIRMED[0]}
    | WORK_REVIEWED[1]
    | MEMO_ANSWERED[1]
    | PAYMENT_CONFIRMED[1]
    | WITHDRAWN
)


@dataclass(frozen=True)
class ResponseTime:
    examples: int
    # Null below MIN_EXAMPLES: not enough to say.
    median_hours: float | None


def waits(
    entries: Iterable[DealRecordEntry], start: str, ends: frozenset[str]
) -> list[float]:
    """Hours from each `start` to the next entry in `ends`, one deal at a time.

    `entries` must be ordered by deal, then by sequence, as the record is.
    """
    hours: list[float] = []
    opened: dict[uuid.UUID, DealRecordEntry] = {}
    for entry in entries:
        memo_id = entry.deal_memo_id
        if entry.kind == start:
            opened[memo_id] = entry
        elif memo_id in opened and entry.kind in ends:
            began = opened.pop(memo_id)
            hours.append((entry.occurred_at - began.occurred_at).total_seconds() / 3600)
        elif entry.kind in WITHDRAWN:
            opened.pop(memo_id, None)
    return hours


def summarise(hours: list[float]) -> ResponseTime:
    if len(hours) < MIN_EXAMPLES:
        return ResponseTime(examples=len(hours), median_hours=None)
    return ResponseTime(
        examples=len(hours), median_hours=round(statistics.median(hours), 1)
    )


def _entries(db: Session, memo_filter: ColumnElement[bool]) -> list[DealRecordEntry]:
    memo_ids = (
        select(DealMemo.id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(memo_filter)
    )
    return list(
        db.scalars(
            select(DealRecordEntry)
            .where(
                DealRecordEntry.deal_memo_id.in_(memo_ids),
                DealRecordEntry.kind.in_(KINDS),
            )
            .order_by(DealRecordEntry.deal_memo_id, DealRecordEntry.sequence)
        )
    )


@dataclass(frozen=True)
class BrandResponseTimes:
    work_reviewed: ResponseTime


@dataclass(frozen=True)
class CreatorResponseTimes:
    memo_answered: ResponseTime
    payment_confirmed: ResponseTime


def for_brand(db: Session, brand_id: uuid.UUID) -> BrandResponseTimes:
    """How long this brand's creators wait for a decision on their work."""
    entries = _entries(db, Campaign.brand_id == brand_id)
    return BrandResponseTimes(work_reviewed=summarise(waits(entries, *WORK_REVIEWED)))


def for_creator(db: Session, creator_id: uuid.UUID) -> CreatorResponseTimes:
    """How long brands wait for this creator's answers."""
    entries = _entries(db, Application.creator_id == creator_id)
    return CreatorResponseTimes(
        memo_answered=summarise(waits(entries, *MEMO_ANSWERED)),
        payment_confirmed=summarise(waits(entries, *PAYMENT_CONFIRMED)),
    )
