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
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
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
