"""Keeping the embedding tables up to date (D-052).

One job: make the stored vector match the profile text it was built from, and
do as little work as possible doing it.

`source_hash` is why. Embedding is by far the slowest thing here — slower than
every query in this project together — so a rebuild that re-embeds rows whose
text has not changed is the difference between seconds and minutes. Every
function below skips a row whose hash still matches, unless told not to.

Nothing here is on the request path. `CLAUDE.md` section 3 says an external
call never blocks a request, and this is the closest thing the project has to
one. Callers run it after a write, or over a batch.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from sqlalchemy import desc, exists, func, null, nulls_last, or_, select
from sqlalchemy.orm import Session

from app.modules.auth import availability_service as availability
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import account_is_active, brand_is_active
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.matching import embedder
from app.modules.matching.embedding_input import campaign_text, creator_text
from app.modules.matching.models import CampaignEmbedding, CreatorEmbedding
from app.modules.payment_status import reliability
from app.modules.payment_status.reliability import ReliabilityRecord


class Rebuilt:
    """What a rebuild did, so a caller can report it honestly."""

    def __init__(self, embedded: int = 0, skipped: int = 0) -> None:
        self.embedded = embedded
        self.skipped = skipped

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return f"Rebuilt(embedded={self.embedded}, skipped={self.skipped})"


class HasId(Protocol):
    """A row this module embeds: it has an id, and a text can be built from it."""

    id: uuid.UUID


def _refresh(
    db: Session,
    rows: Sequence[HasId],
    *,
    model_class: type[CreatorEmbedding] | type[CampaignEmbedding],
    key_name: str,
    to_text: Callable[[Any], str],
    force: bool,
) -> Rebuilt:
    """Embed the rows whose text changed, and leave the rest alone."""
    existing: dict[uuid.UUID, Any] = {
        getattr(row, key_name): row for row in db.scalars(select(model_class)).all()
    }

    pending: list[tuple[uuid.UUID, str, str]] = []
    skipped = 0
    for row in rows:
        key = row.id
        text = to_text(row)
        digest = embedder.source_hash(text)
        current = existing.get(key)
        unchanged = (
            current is not None
            and current.source_hash == digest
            and current.model == embedder.MODEL_NAME
        )
        if unchanged and not force:
            skipped += 1
            continue
        pending.append((key, text, digest))

    if not pending:
        return Rebuilt(embedded=0, skipped=skipped)

    # One call for the whole batch: a model encodes many texts far faster than
    # one at a time, and this is the only slow step.
    vectors = embedder.embed([text for _, text, _ in pending])

    for (key, _, digest), vector in zip(pending, vectors, strict=True):
        current = existing.get(key)
        if current is None:
            db.add(
                model_class(
                    **{key_name: key},
                    embedding=vector,
                    source_hash=digest,
                    model=embedder.MODEL_NAME,
                )
            )
        else:
            current.embedding = vector
            current.source_hash = digest
            current.model = embedder.MODEL_NAME

    return Rebuilt(embedded=len(pending), skipped=skipped)


def refresh_creators(
    db: Session,
    *,
    creator_ids: Sequence[uuid.UUID] | None = None,
    force: bool = False,
    discoverable_only: bool = True,
) -> Rebuilt:
    """Bring creator embeddings up to date. All of them, or the ones named.

    **Only creators who published their Passport, by default.** An embedding
    for someone who cannot be matched is derived personal data we would be
    holding for no purpose, and compute spent for no result. When they
    publish, the next run picks them up; when they unpublish, the row stops
    being reachable through `find_creators_for_campaign` immediately, because
    the filter is on the query rather than on what is stored.
    """
    query = select(Creator)
    if discoverable_only:
        query = query.where(
            Creator.passport_published_at.is_not(None),
            account_is_active(Creator.account_id),
        )
    if creator_ids is not None:
        query = query.where(Creator.id.in_(creator_ids))
    return _refresh(
        db,
        db.scalars(query).all(),
        model_class=CreatorEmbedding,
        key_name="creator_id",
        to_text=creator_text,
        force=force,
    )


def refresh_campaigns(
    db: Session, *, campaign_ids: Sequence[uuid.UUID] | None = None, force: bool = False
) -> Rebuilt:
    """Bring campaign embeddings up to date. All of them, or the ones named."""
    query = select(Campaign)
    if campaign_ids is not None:
        query = query.where(Campaign.id.in_(campaign_ids))
    return _refresh(
        db,
        db.scalars(query).all(),
        model_class=CampaignEmbedding,
        key_name="campaign_id",
        to_text=campaign_text,
        force=force,
    )


# --- finding creators for a campaign (D2 and D3) --------------------------


@dataclass(frozen=True)
class MatchReasons:
    """Why this creator came back, in facts a brand can check.

    D3 in the backlog: "the reasons behind every match". Similarity alone is
    unarguable-with — a brand cannot tell whether 0.83 is good — so the
    reasons that decided it are returned beside it, and most of them are
    structural rather than learned.
    """

    shared_niches: list[str]
    city: str
    accepted_deals: int
    similarity: float | None
    # None when the creator is taking work today (D-083).
    booked_until: date | None = None


@dataclass(frozen=True)
class CreatorMatch:
    creator: Creator
    reasons: MatchReasons


def find_creators_for_campaign(
    db: Session, campaign: Campaign, *, limit: int, today: date
) -> list[CreatorMatch]:
    """Creators worth showing a brand for this campaign, best first.

    **Structural filter first, similarity only to rank inside it.** A brand
    does not want the semantically closest creator in Tamil Nadu; it wants one
    in a city it ships to, in a relevant niche, and among those the best fit.
    City and niche are facts, and getting them from a vector would be both
    worse and unexplainable.

    **Only creators who published their Passport.** D-036 settled that a
    creator who signed up to browse campaigns has not asked to be findable by
    strangers, and a brand searching for someone who never applied is exactly
    that. The same reasoning, and the same free-safe-default argument, applies
    here.

    **It degrades rather than fails.** A campaign whose embedding has not been
    built yet still gets matches, ordered by the structural signals, with
    `similarity` null. Embedding inside a request is not an option: the model
    takes 23 seconds to load and a single vector over 200 ms, both beyond the
    budget (see embedder.py).

    **Free before booked.** Creators taking work `today` come first; a booked
    creator still appears, after them, with the date (D-083), because a
    campaign may run after the booking ends.
    """
    accepted_deals = (
        select(func.count(DealMemo.id))
        .join(Application, Application.id == DealMemo.application_id)
        .where(Application.creator_id == Creator.id, DealMemo.status == "accepted")
        .correlate(Creator)
        .scalar_subquery()
    )

    # The vector is read inside the query, never fetched and sent back: as a
    # parameter its 1,024 numbers cost about 50 ms a call, read in SQL about
    # 1 ms (measured 30 September). Only whether it exists is asked first,
    # since that decides the order.
    has_vector = bool(
        db.scalar(select(exists().where(CampaignEmbedding.campaign_id == campaign.id)))
    )
    campaign_vector = (
        select(CampaignEmbedding.embedding)
        .where(CampaignEmbedding.campaign_id == campaign.id)
        .scalar_subquery()
    )
    distance = (
        CreatorEmbedding.embedding.cosine_distance(campaign_vector)
        if has_vector
        else null()
    )

    query = (
        select(Creator, accepted_deals.label("accepted_deals"), distance.label("d"))
        .outerjoin(CreatorEmbedding, CreatorEmbedding.creator_id == Creator.id)
        .where(
            Creator.passport_published_at.is_not(None),
            # A suspended creator is never suggested (D-061).
            account_is_active(Creator.account_id),
            Creator.city.in_(campaign.cities),
            Creator.niches.overlap(campaign.niches),
        )
    )
    # Closest first when there is a vector to compare against; a creator with
    # no embedding sorts last rather than disappearing. The clause is built as
    # a list rather than passed conditionally, because `order_by(None, ...)`
    # emits a literal `ORDER BY NULL`, which Postgres refuses.
    booked = availability.free_on(today).is_(False)
    order: list[Any] = [booked]
    if has_vector:
        order.append(nulls_last(distance.asc()))
    order += [desc("accepted_deals"), Creator.id]
    query = query.order_by(*order).limit(limit)

    wanted = set(campaign.niches)
    matches = []
    for creator, deals, d in db.execute(query).all():
        matches.append(
            CreatorMatch(
                creator=creator,
                reasons=MatchReasons(
                    shared_niches=sorted(wanted & set(creator.niches)),
                    city=creator.city,
                    accepted_deals=deals,
                    # Cosine distance on normalised vectors: 0 is identical.
                    similarity=None if d is None else round(1.0 - float(d), 4),
                    booked_until=availability.booked_until_shown(
                        creator.booked_until, today
                    ),
                ),
            )
        )
    return matches


# --- the creator's side: campaigns that suit me --------------------------------


@dataclass(frozen=True)
class CampaignMatchReasons:
    """Why this campaign was suggested to a creator, in facts they can check.

    `brand_payments` is the one a creator weighs most: before spending a week
    on someone's brief, whether that brand pays. It is the same record the
    brand's own reliability page shows (D-027), never a separate opinion.
    """

    shared_niches: list[str]
    city: str
    similarity: float | None
    brand_payments: ReliabilityRecord


@dataclass(frozen=True)
class CampaignMatch:
    campaign: Campaign
    reasons: CampaignMatchReasons


def find_campaigns_for_creator(
    db: Session, creator: Creator, *, today: date, record_day: date, limit: int
) -> list[CampaignMatch]:
    """Open campaigns worth this creator's time, best first.

    The mirror of `find_creators_for_campaign`, with the same rules in the
    same order: **the structural filter decides who is in, similarity only
    ranks inside it.** A campaign must name the creator's city and share a
    niche with them; a vector never overrides either.

    Left out: campaigns that are not open, a suspended brand's (D-061), those
    whose applications closed before `today` (the same test applying uses, so
    nothing is suggested that would then be refused), and any the creator
    has already applied to, whatever became of it.

    Unlike the brand's side, the creator need not have published their
    Passport: this is their own view, and nothing about them is shown to
    anyone. An unpublished creator has no embedding (D-052 embeds published
    ones), so their list is ordered newest first and `similarity` is null.

    `record_day` is the Tamil Nadu date the payment records are read as of,
    as on the brand's reliability page; `today` is the date applying checks.
    """
    # The vector is read inside the query, never fetched and sent back: as a
    # parameter its 1,024 numbers cost about 50 ms a call, read in SQL about
    # 1 ms (measured 30 September). Only whether it exists is asked first,
    # since that decides the order.
    has_vector = bool(
        db.scalar(select(exists().where(CreatorEmbedding.creator_id == creator.id)))
    )
    creator_vector = (
        select(CreatorEmbedding.embedding)
        .where(CreatorEmbedding.creator_id == creator.id)
        .scalar_subquery()
    )
    distance = (
        CampaignEmbedding.embedding.cosine_distance(creator_vector)
        if has_vector
        else null()
    )
    already_applied = exists().where(
        Application.campaign_id == Campaign.id, Application.creator_id == creator.id
    )
    query = (
        select(Campaign, distance.label("d"))
        .outerjoin(CampaignEmbedding, CampaignEmbedding.campaign_id == Campaign.id)
        .where(
            Campaign.status == "open",
            brand_is_active(Campaign.brand_id),
            or_(
                Campaign.applications_close_on.is_(None),
                Campaign.applications_close_on >= today,
            ),
            Campaign.cities.any_() == creator.city,
            Campaign.niches.overlap(creator.niches),
            ~already_applied,
        )
    )
    # Closest first when there is a vector; a campaign not yet embedded sorts
    # last rather than disappearing. Newest first breaks ties, and orders the
    # whole list when the creator has no vector at all.
    order: list[Any] = []
    if has_vector:
        order.append(nulls_last(distance.asc()))
    order += [Campaign.created_at.desc(), Campaign.id]
    rows = db.execute(query.order_by(*order).limit(limit)).all()

    records = reliability.for_brands(
        db, {campaign.brand_id for campaign, _ in rows}, record_day
    )
    offered = set(creator.niches)
    return [
        CampaignMatch(
            campaign=campaign,
            reasons=CampaignMatchReasons(
                shared_niches=sorted(offered & set(campaign.niches)),
                city=creator.city,
                similarity=None if d is None else round(1.0 - float(d), 4),
                brand_payments=records[campaign.brand_id],
            ),
        )
        for campaign, d in rows
    ]
