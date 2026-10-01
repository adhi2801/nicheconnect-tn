"""Cleaning proof files before a brand sees them (D-065, decision 1).

A photo carries more than pixels: GPS location, the phone's make and serial
number, the time it was taken, sometimes a thumbnail of the uncropped
original. A proof photo is often taken at home. So every image is decoded and
encoded again from its pixels alone, and only that clean copy is kept.

What is checked, in order, and why:

1. **The bytes are the ones declared.** S3 enforced the fingerprint on
   upload; hashing again here means nothing rests on that alone.
2. **It is the image type declared**, read from the bytes, not trusted from
   the name. A file that only claims to be a PNG is refused.
3. **It is not absurdly large** in pixels, checked from the header before
   anything is decoded: a small file can declare an enormous image and
   exhaust memory (a "decompression bomb").

Then the image is turned the right way up (phones store rotation as
metadata, which is about to be removed), scaled to at most 4096 pixels on
its longest side (more than any screen shows; less memory, less storage),
and saved with no metadata except its colour profile, which is not personal
and keeps colours right.

The order of writes makes a crash harmless: the clean copy is written under
a key fixed by the file's id, so a rerun overwrites it; the database and
the deal record change in one transaction; the original is deleted last,
and one left behind by a crash expires under the bucket's rule for
abandoned uploads.
"""

import hashlib
import io
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import FileStore
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import MAX_PROOF_FILE_BYTES, ProofFile

CLEAN_PREFIX = "proof-files/clean"
# 50 megapixels: above every phone photo but the rare 108 and 200 MP modes,
# which a creator does not need for proof. Checked before decoding.
MAX_PIXELS = 50_000_000
MAX_SIDE = 4096
JPEG_QUALITY = 90
WEBP_QUALITY = 90

# What the bytes say they are, against what the upload declared. MPO is the
# multi-picture JPEG some phones write; it is a JPEG to every viewer.
DETECTED_TYPES = {
    "JPEG": "image/jpeg",
    "MPO": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

CLEANED = "cleaned"
REJECTED = "rejected"
SKIPPED = "skipped"


class Refused(Exception):
    """This file cannot be shown; `reason` is one of PROOF_FILE_REJECTIONS."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Cleaned:
    data: bytes
    sha256: str


def clean_image(data: bytes, content_type: str) -> Cleaned:
    """The same picture, right way up, with no metadata but its colour profile.

    Pure: bytes in, bytes out, so it is tested without a database or a store.
    """
    try:
        with warnings.catch_warnings():
            # Pillow only warns about a large image; here that is a refusal.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as opened:
                if DETECTED_TYPES.get(opened.format or "") != content_type:
                    raise Refused("not_an_image")
                width, height = opened.size
                if width * height > MAX_PIXELS:
                    raise Refused("too_many_pixels")
                if content_type == "image/jpeg":
                    # Decode a large JPEG at a reduced scale directly: far
                    # less memory than decoding in full and shrinking after.
                    opened.draft("RGB", (MAX_SIDE, MAX_SIDE))
                opened.load()
                icc_profile = opened.info.get("icc_profile")
                image = ImageOps.exif_transpose(opened)
    except Refused:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise Refused("too_many_pixels") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        # Not an image, truncated, or corrupt: Pillow raises any of these.
        raise Refused("not_an_image") from None

    image.thumbnail((MAX_SIDE, MAX_SIDE))
    # Start from nothing: whatever Pillow kept in `info` (EXIF, XMP, PNG
    # text, comments) is dropped, and only the colour profile goes back.
    image.info = {}
    extras = {"icc_profile": icc_profile} if icc_profile else {}
    out = io.BytesIO()
    if content_type == "image/jpeg":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, **extras)
    elif content_type == "image/png":
        image.save(out, "PNG", optimize=True, **extras)
    else:
        image.save(out, "WEBP", quality=WEBP_QUALITY, **extras)
    cleaned = out.getvalue()
    return Cleaned(data=cleaned, sha256=hashlib.sha256(cleaned).hexdigest())


def clean_one(db: Session, store: FileStore, file_id: uuid.UUID, now: datetime) -> str:
    """Clean one attached file, or refuse it. Commits; returns what happened.

    `SKIP LOCKED`: if another worker holds this file, it is theirs and this
    call does nothing. A file no longer `attached` has been dealt with.
    """
    file = db.scalars(
        select(ProofFile)
        .where(ProofFile.id == file_id, ProofFile.status == "attached")
        .with_for_update(skip_locked=True)
    ).first()
    if file is None:
        db.rollback()
        return SKIPPED

    try:
        if store.describe(file.storage_key) is None:
            raise Refused("missing")
        data = store.read(file.storage_key, max_bytes=MAX_PROOF_FILE_BYTES)
        if hashlib.sha256(data).hexdigest() != file.sha256:
            raise Refused("fingerprint_mismatch")
        cleaned = clean_image(data, file.content_type)
    except Refused as refusal:
        file.status = REJECTED
        file.rejection_reason = refusal.reason
        file.updated_at = now
        db.commit()
        # A file that will never be shown is not kept.
        if refusal.reason != "missing":
            store.delete(file.storage_key)
        return REJECTED

    clean_key = f"{CLEAN_PREFIX}/{file.id}.{EXTENSIONS[file.content_type]}"
    store.write(clean_key, cleaned.data, content_type=file.content_type)
    file.status = CLEANED
    file.clean_key = clean_key
    file.clean_sha256 = cleaned.sha256
    file.clean_size_bytes = len(cleaned.data)
    file.cleaned_at = now
    file.updated_at = now
    memo = db.get(DealMemo, file.deal_memo_id)
    if memo is None:  # pragma: no cover - RESTRICT makes this impossible
        raise RuntimeError(f"proof file {file.id} has no deal memo")
    record.append(
        db,
        memo,
        kind="proof_file_cleaned",
        actor_role="system",
        now=now,
        facts={
            "file_id": str(file.id),
            "proof_id": str(file.proof_id),
            "content_type": file.content_type,
            # As uploaded, and as the brand will see it.
            "sha256": file.sha256,
            "clean_sha256": cleaned.sha256,
            "clean_size_bytes": len(cleaned.data),
        },
    )
    db.commit()
    store.delete(file.storage_key)
    return CLEANED


@dataclass(frozen=True)
class CleaningRun:
    cleaned: int
    rejected: int
    skipped: int


def clean_attached(
    db: Session, store: FileStore, now: datetime, *, limit: int = 20
) -> CleaningRun:
    """Work through the queue, oldest first, each file in its own transaction.

    One bad file never stops the rest: it is refused on its own and the run
    goes on.
    """
    queue = list(
        db.scalars(
            select(ProofFile.id)
            .where(ProofFile.status == "attached")
            .order_by(ProofFile.attached_at, ProofFile.id)
            .limit(limit)
        ).all()
    )
    db.rollback()
    outcomes = [clean_one(db, store, file_id, now) for file_id in queue]
    return CleaningRun(
        cleaned=outcomes.count(CLEANED),
        rejected=outcomes.count(REJECTED),
        skipped=outcomes.count(SKIPPED),
    )
