"""The embedding tables: one vector per creator and per campaign (D-052).

These run against real Postgres with pgvector, because the things worth
checking — that a `vector(1024)` column refuses a vector of the wrong width,
and that CASCADE actually fires — are database behaviour, not Python.
"""

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DataError, IntegrityError

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
from app.modules.matching.models import (
    EMBEDDING_DIMENSIONS,
    CampaignEmbedding,
    CreatorEmbedding,
)
from tests.factories import build_campaign, build_creator

MODEL = "Qwen/Qwen3-Embedding-0.6B"
SOURCE_HASH = "a" * 64


def a_vector(dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return [0.1] * dimensions


def saved_creator(db) -> Creator:
    creator = build_creator(db, handle=f"emb{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    return creator


def test_a_creator_embedding_is_stored_and_read_back(db):
    creator = saved_creator(db)
    db.add(
        CreatorEmbedding(
            creator_id=creator.id,
            embedding=a_vector(),
            source_hash=SOURCE_HASH,
            model=MODEL,
        )
    )
    db.flush()
    db.expire_all()

    row = db.get(CreatorEmbedding, creator.id)

    assert len(row.embedding) == EMBEDDING_DIMENSIONS
    assert row.model == MODEL
    assert row.created_at is not None


def test_a_campaign_embedding_is_stored_and_read_back(db):
    campaign = build_campaign(db, status="open")
    db.add(campaign)
    db.flush()
    db.add(
        CampaignEmbedding(
            campaign_id=campaign.id,
            embedding=a_vector(),
            source_hash=SOURCE_HASH,
            model=MODEL,
        )
    )
    db.flush()

    assert db.get(CampaignEmbedding, campaign.id) is not None


def test_a_vector_of_the_wrong_width_is_refused(db):
    """The column is vector(1024). A model swap that changes width must fail
    loudly here rather than store something nothing can compare against."""
    creator = saved_creator(db)
    db.add(
        CreatorEmbedding(
            creator_id=creator.id,
            embedding=a_vector(768),
            source_hash=SOURCE_HASH,
            model="some/other-model",
        )
    )

    with pytest.raises((DataError, IntegrityError)):
        db.flush()


def test_one_embedding_per_creator(db):
    """creator_id is the primary key: a second row for the same creator is a
    rebuild that should have been an update."""
    creator = saved_creator(db)
    for _ in range(2):
        db.add(
            CreatorEmbedding(
                creator_id=creator.id,
                embedding=a_vector(),
                source_hash=SOURCE_HASH,
                model=MODEL,
            )
        )

    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_the_creator_takes_the_embedding_with_it(db):
    """Derived data: an embedding without its subject is meaningless, and it
    must never be the reason a deletion is refused."""
    creator = saved_creator(db)
    db.add(
        CreatorEmbedding(
            creator_id=creator.id,
            embedding=a_vector(),
            source_hash=SOURCE_HASH,
            model=MODEL,
        )
    )
    db.flush()

    db.execute(delete(Creator).where(Creator.id == creator.id))
    db.flush()

    remaining = db.scalars(
        select(CreatorEmbedding).where(CreatorEmbedding.creator_id == creator.id)
    ).all()
    assert remaining == []


def test_deleting_the_campaign_takes_its_embedding_with_it(db):
    campaign = build_campaign(db, status="open")
    db.add(campaign)
    db.flush()
    db.add(
        CampaignEmbedding(
            campaign_id=campaign.id,
            embedding=a_vector(),
            source_hash=SOURCE_HASH,
            model=MODEL,
        )
    )
    db.flush()

    db.execute(delete(Campaign).where(Campaign.id == campaign.id))
    db.flush()

    remaining = db.scalars(
        select(CampaignEmbedding).where(CampaignEmbedding.campaign_id == campaign.id)
    ).all()
    assert remaining == []


def test_cosine_distance_works_against_a_stored_vector(db):
    """The whole point of the column type: pgvector can compare it in SQL.

    Proves the extension is enabled and the operator is available, which is
    what the migration is really for.
    """
    creator = saved_creator(db)
    db.add(
        CreatorEmbedding(
            creator_id=creator.id,
            embedding=a_vector(),
            source_hash=SOURCE_HASH,
            model=MODEL,
        )
    )
    db.flush()

    distance = db.scalar(
        select(CreatorEmbedding.embedding.cosine_distance(a_vector())).where(
            CreatorEmbedding.creator_id == creator.id
        )
    )

    assert distance == pytest.approx(0.0, abs=1e-6)
