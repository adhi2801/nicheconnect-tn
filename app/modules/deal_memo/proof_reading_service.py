"""Reading cleaned proof files, checking what they say, sealing it (D-070).

Layer 1 reads (`proof_reader`); this module runs layers 2 and 3: the checks
against facts we already hold, and the seal in the deal record. The checks
are plain rules, no AI:

- **The handle matches** the creator's linked channel on that platform.
- **The post date falls inside the deal**: on or after the day the memo was
  accepted, and not after today (in Tamil Nadu).
- **The numbers agree with each other**: likes, comments, saves, shares and
  reach never above views, reach never above impressions.
- **What the creator claimed** about that channel (followers, average views)
  is copied in beside the reading, so a later profile edit cannot change the
  comparison.

A check with nothing to compare against is left empty, never passed.

**No network call inside a transaction** (database.md section 7). A file is
claimed with a Postgres advisory lock, held on a connection of its own for
the whole read, so it is never tied to a pooled connection somebody else
may get. The screenshot is fetched and read with no transaction open; the
result and its seal are then written in one short transaction. Two runs
that overlap never read the same file twice.

A failed reading is retried (an unreachable API, a cut-off answer) up to
three times, a quarter of an hour apart; a refusal or an answer out of shape
is final. Readings stop at the daily limit in settings, a ceiling on the
bill.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.config import settings
from app.core.storage import FileStore, ObjectTooLarge
from app.modules.auth.models.rate_card import CreatorChannel
from app.modules.campaigns.models import Application
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.exceptions import (
    ProofReadingAlreadyMarked,
    ProofReadingNotFound,
    ProofReadingNotMarkable,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof, ProofFile
from app.modules.deal_memo.proof_reader import Reading, ScreenshotReader
from app.modules.deal_memo.proof_reading_models import ProofFileReading

logger = logging.getLogger(__name__)

# Screenshots read per run. A run starts every minute; a reading takes
# seconds, so five keep a run near a minute even when the API is slow.
PER_RUN = 5
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=15)
RETRYABLE = ("api_error", "max_tokens")
# The clean copy is at most 4096 px on its long side (D-065); this is far
# above any such image, and only stops a runaway read.
MAX_CLEAN_BYTES = 40_000_000
# The first half of every advisory lock this module takes, so its locks can
# never collide with another module's.
LOCK_NAMESPACE = 70_070

READ = "read"
NO_NUMBERS = "no_numbers"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class Checks:
    handle_matches: bool | None
    date_within_deal: bool | None
    numbers_consistent: bool | None
    stated_followers: int | None
    stated_average_views: int | None


@dataclass(frozen=True)
class ReadingRun:
    read: int
    no_numbers: int
    failed: int
    skipped: int
    stopped_at_limit: bool


def handle_from_profile_url(platform: str, url: str) -> str | None:
    """The handle in a channel link, when the link names one.

    instagram.com/priya.eats and youtube.com/@priya.eats do; a YouTube
    /channel/ or /c/ link does not, and then there is nothing to compare.
    """
    segments = [part for part in urlparse(url).path.split("/") if part]
    if not segments:
        return None
    first = segments[0].lower()
    if platform == "instagram":
        return first
    if platform == "youtube" and first.startswith("@") and len(first) > 1:
        return first[1:]
    return None


def numbers_agree(numbers: dict[str, int]) -> bool | None:
    """Whether the counts are possible together; None with no pair to compare."""
    pairs = [
        (small, big)
        for small, big in (
            ("likes", "views"),
            ("comments", "views"),
            ("saves", "views"),
            ("shares", "views"),
            ("reach", "views"),
            ("reach", "impressions"),
        )
        if small in numbers and big in numbers
    ]
    if not pairs:
        return None
    return all(numbers[small] <= numbers[big] for small, big in pairs)


def check_reading(
    reading: Reading, memo: DealMemo, channel: CreatorChannel | None, today: date
) -> Checks:
    """Layer 2: what the reading says, against what we hold."""
    channel_handle = (
        handle_from_profile_url(channel.platform, channel.profile_url)
        if channel
        else None
    )
    handle_matches = (
        reading.handle == channel_handle if reading.handle and channel_handle else None
    )
    date_within_deal = None
    if reading.post_date and memo.accepted_at:
        accepted_on = india_date(memo.accepted_at)
        date_within_deal = accepted_on <= reading.post_date <= today
    return Checks(
        handle_matches=handle_matches,
        date_within_deal=date_within_deal,
        numbers_consistent=numbers_agree(reading.numbers or {}),
        stated_followers=channel.followers if channel else None,
        stated_average_views=channel.average_views if channel else None,
    )


def creator_channel(
    db: Session, memo: DealMemo, platform: str | None
) -> CreatorChannel | None:
    if platform not in ("instagram", "youtube"):
        return None
    return db.scalars(
        select(CreatorChannel)
        .join(Application, Application.creator_id == CreatorChannel.creator_id)
        .where(Application.id == memo.application_id, CreatorChannel.platform == platform)
    ).first()


def due(now: datetime) -> ColumnElement[bool]:
    """Cleaned files never read, or whose last reading failed and may be retried."""
    return and_(
        ProofFile.status == "cleaned",
        or_(
            ProofFileReading.id.is_(None),
            and_(
                ProofFileReading.status == "failed",
                ProofFileReading.failure.in_(RETRYABLE),
                ProofFileReading.attempts < MAX_ATTEMPTS,
                ProofFileReading.read_at <= now - RETRY_AFTER,
            ),
        ),
    )


def readings_in_last_day(db: Session, now: datetime) -> int:
    count = db.scalar(
        select(func.count(ProofFileReading.id)).where(
            ProofFileReading.read_at > now - timedelta(days=1)
        )
    )
    return int(count or 0)


def save_reading(db: Session, file_id: uuid.UUID, reading: Reading, now: datetime) -> str:
    """Write one reading and, unless it failed, seal it. Commits."""
    file = db.scalars(
        select(ProofFile)
        .outerjoin(ProofFileReading, ProofFileReading.proof_file_id == ProofFile.id)
        .where(ProofFile.id == file_id, due(now))
        .with_for_update(of=ProofFile)
    ).first()
    if file is None:
        # Read by someone else meanwhile, or no longer due.
        db.rollback()
        return SKIPPED
    memo = db.get(DealMemo, file.deal_memo_id)
    if memo is None:  # pragma: no cover - RESTRICT makes this impossible
        raise RuntimeError(f"proof file {file.id} has no deal memo")
    checks = check_reading(
        reading, memo, creator_channel(db, memo, reading.platform), india_date(now)
    )
    row = db.scalars(
        select(ProofFileReading).where(ProofFileReading.proof_file_id == file.id)
    ).first()
    if row is None:
        row = ProofFileReading(proof_file_id=file.id, attempts=1)
        db.add(row)
    else:
        row.attempts += 1
    numbers = reading.numbers or {}
    row.status = reading.status
    row.failure = reading.failure
    row.model = reading.model
    row.prompt_version = reading.prompt_version
    row.platform = reading.platform
    row.handle = reading.handle
    row.post_date = reading.post_date
    for metric in (
        "views",
        "reach",
        "impressions",
        "likes",
        "comments",
        "saves",
        "shares",
    ):
        setattr(row, metric, numbers.get(metric))
    row.abbreviated = list(reading.abbreviated)
    row.handle_matches = checks.handle_matches
    row.date_within_deal = checks.date_within_deal
    row.numbers_consistent = checks.numbers_consistent
    row.stated_followers = checks.stated_followers
    row.stated_average_views = checks.stated_average_views
    row.input_tokens = reading.input_tokens
    row.output_tokens = reading.output_tokens
    row.read_at = now
    row.updated_at = now
    if reading.status != FAILED:
        record.append(
            db,
            memo,
            kind="proof_results_read",
            actor_role="system",
            now=now,
            facts={
                "file_id": str(file.id),
                "proof_id": str(file.proof_id),
                # The copy that was read: the one the brand sees (D-066).
                "clean_sha256": file.clean_sha256,
                "status": reading.status,
                "model": reading.model,
                "prompt_version": reading.prompt_version,
                "platform": reading.platform,
                "handle": reading.handle,
                "post_date": reading.post_date.isoformat() if reading.post_date else None,
                "numbers": numbers,
                "abbreviated": list(reading.abbreviated),
                "checks": {
                    "handle_matches": checks.handle_matches,
                    "date_within_deal": checks.date_within_deal,
                    "numbers_consistent": checks.numbers_consistent,
                    "stated_followers": checks.stated_followers,
                    "stated_average_views": checks.stated_average_views,
                },
            },
        )
    db.commit()
    return reading.status


def read_one(
    db: Session,
    store: FileStore,
    reader: ScreenshotReader,
    file_id: uuid.UUID,
    now: datetime,
) -> str:
    """Claim, read, check and seal one file. Returns what happened."""
    lock_key = func.hashtext(str(file_id))
    with db.get_bind().engine.connect() as lock:
        claimed = lock.scalar(select(func.pg_try_advisory_lock(LOCK_NAMESPACE, lock_key)))
        lock.commit()
        if not claimed:
            return SKIPPED
        try:
            file = db.scalars(
                select(ProofFile)
                .outerjoin(
                    ProofFileReading, ProofFileReading.proof_file_id == ProofFile.id
                )
                .where(ProofFile.id == file_id, due(now))
            ).first()
            if file is None or file.clean_key is None:
                db.rollback()
                return SKIPPED
            clean_key, content_type = file.clean_key, file.content_type
            # Nothing held open while storage and the API are called.
            db.rollback()
            try:
                image = store.read(clean_key, max_bytes=MAX_CLEAN_BYTES)
            except KeyError, ObjectTooLarge:
                logger.warning("proof file %s: its clean copy cannot be read", file_id)
                return SKIPPED
            reading = reader.read(image, content_type)
            return save_reading(db, file_id, reading, now)
        finally:
            lock.execute(select(func.pg_advisory_unlock(LOCK_NAMESPACE, lock_key)))
            lock.commit()


def read_due(
    db: Session,
    store: FileStore,
    reader: ScreenshotReader | None,
    now: datetime,
    *,
    limit: int = PER_RUN,
) -> ReadingRun:
    """One run: the oldest due files, each on its own, up to the daily limit.

    With reading switched off (no reader) nothing happens at all.
    """
    if reader is None:
        return ReadingRun(
            read=0, no_numbers=0, failed=0, skipped=0, stopped_at_limit=False
        )
    allowance = settings.proof_reading_daily_limit - readings_in_last_day(db, now)
    if allowance <= 0:
        db.rollback()
        logger.warning("proof reading stopped: the daily limit is reached")
        return ReadingRun(
            read=0, no_numbers=0, failed=0, skipped=0, stopped_at_limit=True
        )
    queue = list(
        db.scalars(
            select(ProofFile.id)
            .outerjoin(ProofFileReading, ProofFileReading.proof_file_id == ProofFile.id)
            .where(due(now))
            .order_by(ProofFile.cleaned_at, ProofFile.id)
            .limit(min(limit, allowance))
        ).all()
    )
    db.rollback()
    outcomes = [read_one(db, store, reader, file_id, now) for file_id in queue]
    return ReadingRun(
        read=outcomes.count(READ),
        no_numbers=outcomes.count(NO_NUMBERS),
        failed=outcomes.count(FAILED),
        skipped=outcomes.count(SKIPPED),
        stopped_at_limit=False,
    )


# --- showing readings, and the creator's mark (step 5) -------------------------------------


def views_against_stated(row: ProofFileReading) -> float | None:
    """Views read, or reach when no views were shown, over the creator's own
    stated average views at the time of reading. None with nothing to compare.

    1.0 is exactly what they claim; 0.1 is a tenth of it; 9.0 is nine times.
    """
    observed = row.views if row.views is not None else row.reach
    if observed is None or not row.stated_average_views:
        return None
    return round(observed / row.stated_average_views, 2)


def shown_readings(
    db: Session, file_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ProofFileReading]:
    """The readings to show for these files, in one query.

    A failed reading is not shown: to both sides that file is simply not read
    yet, and it may still be retried.
    """
    if not file_ids:
        return {}
    rows = db.scalars(
        select(ProofFileReading).where(
            ProofFileReading.proof_file_id.in_(file_ids),
            ProofFileReading.status != FAILED,
        )
    ).all()
    return {row.proof_file_id: row for row in rows}


def mark_misread(
    db: Session,
    proof: DeliverableProof,
    file_id: uuid.UUID,
    note: str,
    now: datetime,
) -> ProofFileReading:
    """The creator says this reading is wrong. Kept beside it, never instead.

    Once per reading, and only on numbers that were read. Commits.
    """
    row = db.scalars(
        select(ProofFileReading)
        .join(ProofFile, ProofFile.id == ProofFileReading.proof_file_id)
        .where(
            ProofFile.id == file_id,
            ProofFile.proof_id == proof.id,
            ProofFileReading.status != FAILED,
        )
        .with_for_update(of=ProofFileReading)
    ).first()
    if row is None:
        raise ProofReadingNotFound()
    if row.status != READ:
        raise ProofReadingNotMarkable()
    if row.creator_marked_at is not None:
        raise ProofReadingAlreadyMarked()
    row.creator_marked_at = now
    row.creator_note = note
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row
