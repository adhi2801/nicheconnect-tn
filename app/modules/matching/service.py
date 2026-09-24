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
from typing import Any, Protocol

from sqlalchemy import desc, func, null, nulls_last, select
from sqlalchemy.orm import Session

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.matching import embedder
from app.modules.matching.embedding_input import campaign_text, creator_text
from app.modules.matching.models import CampaignEmbedding, CreatorEmbedding


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
    db: Session, *, creator_ids: Sequence[uuid.UUID] | None = None, force: bool = False
) -> Rebuilt:
    """Bring creator embeddings up to date. All of them, or the ones named."""
    query = select(Creator)
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


@dataclass(frozen=True)
class CreatorMatch:
    creator: Creator
    reasons: MatchReasons


def find_creators_for_campaign(
    db: Session, campaign: Campaign, *, limit: int
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
    """
    accepted_deals = (
        select(func.count(DealMemo.id))
        .join(Application, Application.id == DealMemo.application_id)
        .where(Application.creator_id == Creator.id, DealMemo.status == "accepted")
        .correlate(Creator)
        .scalar_subquery()
    )

    campaign_vector = db.scalar(
        select(CampaignEmbedding.embedding).where(
            CampaignEmbedding.campaign_id == campaign.id
        )
    )
    distance = (
        CreatorEmbedding.embedding.cosine_distance(campaign_vector)
        if campaign_vector is not None
        else null()
    )

    query = (
        select(Creator, accepted_deals.label("accepted_deals"), distance.label("d"))
        .outerjoin(CreatorEmbedding, CreatorEmbedding.creator_id == Creator.id)
        .where(
            Creator.passport_published_at.is_not(None),
            Creator.city.in_(campaign.cities),
            Creator.niches.overlap(campaign.niches),
        )
    )
    # Closest first when there is a vector to compare against; a creator with
    # no embedding sorts last rather than disappearing. The clause is built as
    # a list rather than passed conditionally, because `order_by(None, ...)`
    # emits a literal `ORDER BY NULL`, which Postgres refuses.
    order: list[Any] = []
    if campaign_vector is not None:
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
                ),
            )
        )
    return matches
