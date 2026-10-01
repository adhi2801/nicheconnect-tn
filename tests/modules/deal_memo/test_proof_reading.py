"""Reading cleaned proof files, checking them, sealing them (D-070, layers 1 to 3).

Each test walks the real path: upload through the stand-in's form, submit the
proof, clean it, then read it with a fake reader. Claude is never called.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.core import storage
from app.core.clock import india_date
from app.core.config import settings
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel
from app.modules.deal_memo import proof_cleaning_service as cleaning
from app.modules.deal_memo import proof_reading_service as reading_service
from app.modules.deal_memo.proof_models import ProofFile
from app.modules.deal_memo.proof_reader import PROMPT_VERSION, Reading
from app.modules.deal_memo.proof_reading_models import ProofFileReading
from app.modules.deal_memo.proof_reading_service import (
    LOCK_NAMESPACE,
    handle_from_profile_url,
    numbers_agree,
    read_due,
)
from app.modules.deal_memo.record_models import DealRecordEntry
from tests.deal_flow import User, accepted_memo, brand_user, creator_user
from tests.modules.deal_memo.test_proof_cleaning import photo, submitted

NUMBERS = {"views": 48210, "reach": 31400, "likes": 2104}


class FakeReader:
    """Answers with a fixed reading and keeps what it was shown."""

    def __init__(self, **overrides) -> None:
        self.overrides = overrides
        self.images: list[bytes] = []

    def read(self, image: bytes, content_type: str) -> Reading:
        self.images.append(image)
        fields = {
            "status": "read",
            "model": "claude-opus-5-5",
            "prompt_version": PROMPT_VERSION,
            "numbers": dict(NUMBERS),
            "platform": "instagram",
            "handle": "priya.eats",
            "post_date": None,
            "input_tokens": 3400,
            "output_tokens": 400,
        }
        fields.update(self.overrides)
        return Reading(**fields)


@pytest.fixture(autouse=True)
def empty_store() -> Iterator[None]:
    storage.memory_store().clear()
    yield
    storage.memory_store().clear()


@pytest.fixture
def deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    return brand, creator, accepted_memo(client, brand, creator)


def cleaned(client, db, clock, creator: User, memo_id: str, count: int = 1) -> list[str]:
    """Files on a submitted proof, cleaned and ready to read."""
    ids = submitted(
        client,
        clock,
        creator,
        memo_id,
        *[(photo(size=(40 + n, 20)), "image/jpeg") for n in range(count)],
    )
    cleaning.clean_attached(db, storage.memory_store(), clock.now)
    return ids


def channel(db, creator: User, clock, **overrides) -> CreatorChannel:
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    ).one()
    fields = {
        "creator_id": creator_id,
        "platform": "instagram",
        "profile_url": "https://www.instagram.com/priya.eats/",
        "followers": 12000,
        "average_views": 9000,
        "figures_as_of": india_date(clock.now),
    }
    fields.update(overrides)
    row = CreatorChannel(**fields)
    db.add(row)
    db.flush()
    return row


def run(db, clock, reader, **kwargs):
    return read_due(db, storage.memory_store(), reader, clock.now, **kwargs)


def reading_for(db, file_id: str) -> ProofFileReading | None:
    db.expire_all()
    return db.scalars(
        select(ProofFileReading).where(
            ProofFileReading.proof_file_id == uuid.UUID(file_id)
        )
    ).first()


def sealed(db, memo_id: str) -> list[DealRecordEntry]:
    return list(
        db.scalars(
            select(DealRecordEntry).where(
                DealRecordEntry.deal_memo_id == memo_id,
                DealRecordEntry.kind == "proof_results_read",
            )
        ).all()
    )


# --- switched off ------------------------------------------------------------------------


def test_switched_off_nothing_is_read(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    result = run(db, clock, None)

    assert result == reading_service.ReadingRun(0, 0, 0, 0, stopped_at_limit=False)
    assert reading_for(db, file_id) is None


# --- read, checked, sealed ---------------------------------------------------------------


def test_a_cleaned_file_is_read_checked_and_sealed(client, db, clock, deal):
    _, creator, memo_id = deal
    channel(db, creator, clock)
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    reader = FakeReader(post_date=india_date(clock.now))

    result = run(db, clock, reader)

    assert result.read == 1
    row = reading_for(db, file_id)
    assert (row.status, row.views, row.reach, row.likes) == ("read", 48210, 31400, 2104)
    assert (row.handle_matches, row.date_within_deal, row.numbers_consistent) == (
        True,
        True,
        True,
    )
    assert (row.stated_followers, row.stated_average_views) == (12000, 9000)
    assert (row.input_tokens, row.output_tokens, row.attempts) == (3400, 400, 1)
    [entry] = sealed(db, memo_id)
    file = db.get(ProofFile, uuid.UUID(file_id))
    assert entry.actor_role == "system"
    assert entry.facts["clean_sha256"] == file.clean_sha256
    assert entry.facts["numbers"] == NUMBERS
    assert entry.facts["checks"]["handle_matches"] is True


def test_only_the_clean_copy_is_ever_shown_to_the_reader(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    reader = FakeReader()

    run(db, clock, reader)

    file = db.get(ProofFile, uuid.UUID(file_id))
    [shown] = reader.images
    assert shown == storage.memory_store().read(file.clean_key, max_bytes=10_000_000)


def test_a_handle_that_is_not_the_creators_channel_is_flagged(client, db, clock, deal):
    _, creator, memo_id = deal
    channel(db, creator, clock)
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    run(db, clock, FakeReader(handle="someone.else"))

    assert reading_for(db, file_id).handle_matches is False


def test_a_post_dated_before_the_deal_is_flagged(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    run(db, clock, FakeReader(post_date=india_date(clock.now) - timedelta(days=30)))

    assert reading_for(db, file_id).date_within_deal is False


def test_a_post_dated_in_the_future_is_flagged(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    run(db, clock, FakeReader(post_date=india_date(clock.now) + timedelta(days=2)))

    assert reading_for(db, file_id).date_within_deal is False


def test_numbers_that_cannot_be_true_together_are_flagged(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    run(db, clock, FakeReader(numbers={"views": 100, "likes": 5000}))

    assert reading_for(db, file_id).numbers_consistent is False


def test_with_nothing_to_compare_a_check_stays_empty_not_passed(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    run(db, clock, FakeReader(numbers={"views": 100}, handle=None))

    row = reading_for(db, file_id)
    assert (row.handle_matches, row.date_within_deal, row.numbers_consistent) == (
        None,
        None,
        None,
    )
    assert (row.stated_followers, row.stated_average_views) == (None, None)


def test_the_creators_claim_is_copied_so_a_later_edit_changes_nothing(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    claimed = channel(db, creator, clock)
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    run(db, clock, FakeReader())

    claimed.average_views = 90_000
    db.flush()

    assert reading_for(db, file_id).stated_average_views == 9000


def test_a_screen_with_no_numbers_is_sealed_as_such(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    result = run(
        db,
        clock,
        FakeReader(status="no_numbers", numbers=None, platform=None, handle=None),
    )

    assert result.no_numbers == 1
    assert reading_for(db, file_id).status == "no_numbers"
    [entry] = sealed(db, memo_id)
    assert entry.facts["status"] == "no_numbers"


# --- failures and retries -----------------------------------------------------------------


def failure(kind: str) -> FakeReader:
    return FakeReader(
        status="failed", failure=kind, numbers=None, platform=None, handle=None
    )


def test_a_failed_reading_is_kept_but_never_sealed(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    result = run(db, clock, failure("api_error"))

    assert result.failed == 1
    row = reading_for(db, file_id)
    assert (row.status, row.failure, row.attempts) == ("failed", "api_error", 1)
    assert sealed(db, memo_id) == []


def test_an_api_failure_is_retried_after_a_quarter_hour_three_times_at_most(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    reader = failure("api_error")

    run(db, clock, reader)
    run(db, clock, reader)  # too soon
    assert len(reader.images) == 1
    for _ in range(4):
        clock.advance(reading_service.RETRY_AFTER)
        run(db, clock, reader)

    assert len(reader.images) == reading_service.MAX_ATTEMPTS
    assert reading_for(db, file_id).attempts == reading_service.MAX_ATTEMPTS


def test_a_retry_that_succeeds_replaces_the_failure_and_is_sealed(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    run(db, clock, failure("max_tokens"))
    clock.advance(reading_service.RETRY_AFTER)

    run(db, clock, FakeReader())

    row = reading_for(db, file_id)
    assert (row.status, row.failure, row.attempts) == ("read", None, 2)
    assert len(sealed(db, memo_id)) == 1


@pytest.mark.parametrize("final", ["refusal", "invalid_answer", "image_too_large"])
def test_a_final_failure_is_never_retried(client, db, clock, deal, final):
    _, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id)
    reader = failure(final)

    run(db, clock, reader)
    clock.advance(reading_service.RETRY_AFTER * 4)
    run(db, clock, reader)

    assert len(reader.images) == 1


# --- what is due, and what is not ----------------------------------------------------------


def test_a_second_run_finds_nothing_to_read(client, db, clock, deal):
    _, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id)
    reader = FakeReader()
    run(db, clock, reader)

    again = run(db, clock, reader)

    assert again == reading_service.ReadingRun(0, 0, 0, 0, stopped_at_limit=False)
    assert len(reader.images) == 1


def test_files_not_yet_cleaned_are_never_read(client, db, clock, deal):
    _, creator, memo_id = deal
    submitted(client, clock, creator, memo_id, (photo(), "image/jpeg"))
    reader = FakeReader()

    run(db, clock, reader)

    assert reader.images == []


def test_a_run_reads_at_most_its_share_oldest_first(client, db, clock, deal):
    _, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id, count=3)
    reader = FakeReader()

    result = run(db, clock, reader, limit=2)

    assert result.read == 2
    assert run(db, clock, reader).read == 1


def test_reading_stops_at_the_daily_limit(client, db, clock, deal, monkeypatch):
    _, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id, count=2)
    monkeypatch.setattr(settings, "proof_reading_daily_limit", 1)
    reader = FakeReader()

    first = run(db, clock, reader)
    second = run(db, clock, reader)

    assert first.read == 1
    assert second.stopped_at_limit is True
    assert len(reader.images) == 1
    # A day later there is room again.
    clock.advance(timedelta(days=1, seconds=1))
    assert run(db, clock, reader).read == 1


def test_a_file_another_run_is_reading_is_left_to_it(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    reader = FakeReader()
    with db.get_bind().engine.connect() as other_run:
        other_run.execute(
            select(func.pg_advisory_lock(LOCK_NAMESPACE, func.hashtext(file_id)))
        )
        other_run.commit()

        result = run(db, clock, reader)

        other_run.execute(
            select(func.pg_advisory_unlock(LOCK_NAMESPACE, func.hashtext(file_id)))
        )
        other_run.commit()

    assert result.skipped == 1
    assert reader.images == []


def test_no_advisory_lock_is_left_behind(client, db, clock, deal):
    _, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id)

    run(db, clock, FakeReader())

    held = db.scalar(
        text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = :ns"
        ),
        {"ns": LOCK_NAMESPACE},
    )
    assert held == 0


def test_a_clean_copy_gone_from_storage_is_skipped_not_crashed(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    storage.memory_store().delete(db.get(ProofFile, uuid.UUID(file_id)).clean_key)
    reader = FakeReader()

    result = run(db, clock, reader)

    assert result.skipped == 1
    assert reader.images == []
    assert reading_for(db, file_id) is None


# --- the rules on their own --------------------------------------------------------------


@pytest.mark.parametrize(
    ("platform", "url", "handle"),
    [
        ("instagram", "https://www.instagram.com/priya.eats/", "priya.eats"),
        ("instagram", "https://instagram.com/Priya.Eats", "priya.eats"),
        ("youtube", "https://www.youtube.com/@PriyaEats", "priyaeats"),
        ("youtube", "https://www.youtube.com/channel/UC123", None),
        ("youtube", "https://www.youtube.com/@", None),
        ("instagram", "https://www.instagram.com/", None),
    ],
)
def test_the_handle_in_a_channel_link(platform, url, handle):
    assert handle_from_profile_url(platform, url) == handle


@pytest.mark.parametrize(
    ("numbers", "agree"),
    [
        ({"views": 100, "likes": 10, "reach": 80}, True),
        ({"views": 100, "likes": 101}, False),
        ({"reach": 500, "impressions": 400}, False),
        ({"reach": 500, "views": 400}, False),
        ({"views": 100}, None),
        ({}, None),
    ],
)
def test_which_numbers_can_be_true_together(numbers, agree):
    assert numbers_agree(numbers) is agree
