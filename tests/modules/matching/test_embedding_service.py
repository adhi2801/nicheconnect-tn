"""Keeping embeddings in step with the text they were built from (D-052).

These use a fake encoder rather than the real model. That is the point of the
seam in `embedder.set_model`: the suite must not need a 1.2 GB download, and
what is worth testing here is the bookkeeping — what gets embedded, what gets
skipped, what gets rewritten — not whether Qwen3 produces good vectors.

The one thing that does need the real model is that it returns 1024
dimensions, and the column enforces that in
`test_embedding_model.py::test_a_vector_of_the_wrong_width_is_refused`.
"""

import uuid

import pytest

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.modules.matching import embedder, service
from app.modules.matching.embedder import WrongDimensions
from app.modules.matching.models import CampaignEmbedding, CreatorEmbedding
from tests.factories import build_campaign, build_creator


class FakeEncoder:
    """Returns a fixed-width vector and records what it was asked to embed."""

    def __init__(self, dimensions: int = embedder.EXPECTED_DIMENSIONS) -> None:
        self.dimensions = dimensions
        self.seen: list[list[str]] = []

    def encode(self, sentences, **kwargs):
        self.seen.append(list(sentences))
        return [[0.5] * self.dimensions for _ in sentences]

    @property
    def calls(self) -> int:
        return len(self.seen)

    @property
    def texts_embedded(self) -> int:
        return sum(len(batch) for batch in self.seen)


@pytest.fixture
def encoder():
    fake = FakeEncoder()
    embedder.set_model(fake)
    try:
        yield fake
    finally:
        embedder.set_model(None)  # back to lazy loading


def a_creator(db):
    creator = build_creator(db, handle=f"svc{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    return creator


# --- embedding what is missing --------------------------------------------


def test_a_creator_with_no_embedding_gets_one(db, encoder):
    creator = a_creator(db)

    result = service.refresh_creators(db, creator_ids=[creator.id])
    db.flush()

    assert result.embedded == 1
    assert result.skipped == 0
    assert db.get(CreatorEmbedding, creator.id) is not None


def test_a_campaign_with_no_embedding_gets_one(db, encoder):
    campaign = build_campaign(db, status="open")
    db.add(campaign)
    db.flush()

    result = service.refresh_campaigns(db, campaign_ids=[campaign.id])
    db.flush()

    assert result.embedded == 1
    assert db.get(CampaignEmbedding, campaign.id) is not None


def test_it_embeds_the_text_the_input_builder_produced(db, encoder):
    """The seam that keeps constraint 2 meaningful: whatever reaches the model
    is whatever embedding_input decided, not the row."""
    creator = a_creator(db)

    service.refresh_creators(db, creator_ids=[creator.id])

    embedded = encoder.seen[0][0]
    assert f"city: {creator.city}" in embedded
    assert creator.handle not in embedded
    assert creator.display_name not in embedded


# --- not embedding what has not changed ------------------------------------


def test_a_second_run_embeds_nothing(db, encoder):
    """The source_hash win. Embedding is the slow part, so a rebuild that
    re-embeds unchanged rows is the difference between seconds and minutes."""
    creator = a_creator(db)
    service.refresh_creators(db, creator_ids=[creator.id])
    db.flush()

    result = service.refresh_creators(db, creator_ids=[creator.id])

    assert result.embedded == 0
    assert result.skipped == 1
    assert encoder.texts_embedded == 1  # not 2


def test_changing_the_profile_text_re_embeds(db, encoder):
    creator = a_creator(db)
    service.refresh_creators(db, creator_ids=[creator.id])
    db.flush()

    assert creator.city != "Madurai"  # the factory's default is Coimbatore
    creator.city = "Madurai"
    db.flush()
    result = service.refresh_creators(db, creator_ids=[creator.id])

    assert result.embedded == 1
    assert result.skipped == 0


def test_changing_a_field_that_is_not_embedded_does_not_re_embed(db, encoder):
    """display_name is deliberately not embedded, so touching it is free."""
    creator = a_creator(db)
    service.refresh_creators(db, creator_ids=[creator.id])
    db.flush()

    creator.display_name = "A Completely Different Name"
    db.flush()
    result = service.refresh_creators(db, creator_ids=[creator.id])

    assert result.embedded == 0
    assert result.skipped == 1


def test_force_re_embeds_regardless(db, encoder):
    """What a model change needs: the text is the same, the vector is not."""
    creator = a_creator(db)
    service.refresh_creators(db, creator_ids=[creator.id])
    db.flush()

    result = service.refresh_creators(db, creator_ids=[creator.id], force=True)

    assert result.embedded == 1


def test_a_row_embedded_by_another_model_is_rebuilt(db, encoder):
    """`model` on the row is how two models coexist while one replaces the
    other: a row from the old one is not treated as up to date."""
    creator = a_creator(db)
    service.refresh_creators(db, creator_ids=[creator.id])
    db.flush()
    db.get(CreatorEmbedding, creator.id).model = "some/older-model"
    db.flush()

    result = service.refresh_creators(db, creator_ids=[creator.id])

    assert result.embedded == 1


# --- batching and failure --------------------------------------------------


def test_many_creators_are_embedded_in_one_call(db, encoder):
    """A model encodes a batch far faster than one at a time."""
    ids = [a_creator(db).id for _ in range(3)]

    result = service.refresh_creators(db, creator_ids=ids)

    assert result.embedded == 3
    assert encoder.calls == 1


def test_embedding_nothing_calls_no_model(db, encoder):
    result = service.refresh_creators(db, creator_ids=[uuid.uuid4()])

    assert result.embedded == 0
    assert encoder.calls == 0


def test_a_model_returning_the_wrong_width_is_refused():
    """Fails loudly rather than storing something nothing can compare against."""
    embedder.set_model(FakeEncoder(dimensions=768))
    try:
        with pytest.raises(WrongDimensions) as exc_info:
            embedder.embed(["anything"])
        assert "768" in str(exc_info.value)
        assert "migration" in str(exc_info.value)
    finally:
        embedder.set_model(None)


def test_embedding_an_empty_list_never_loads_the_model():
    """Guards the lazy load: the import of torch is the slowest thing here."""
    embedder.set_model(None)

    assert embedder.embed([]) == []


def test_the_source_hash_changes_with_the_text():
    assert embedder.source_hash("city: Madurai") != embedder.source_hash("city: Salem")
    assert embedder.source_hash("city: Madurai") == embedder.source_hash("city: Madurai")
