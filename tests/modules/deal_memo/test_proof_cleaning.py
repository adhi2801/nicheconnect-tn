"""Cleaning proof files: no location or hidden data ever reaches a brand (D-065).

Two halves. `clean_image` is pure, so the privacy promise is tested directly
on real images carrying real metadata: GPS, camera details, PNG text, a
rotation. Then the whole path: upload, submit, clean, and what the store,
the table and the deal record hold afterwards.
"""

import hashlib
import io
from collections.abc import Iterator

import pytest
from PIL import Image, ImageCms
from sqlalchemy import select

from app.core import storage
from app.modules.deal_memo import proof_cleaning_service as cleaning
from app.modules.deal_memo.proof_cleaning_service import Refused, clean_image
from app.modules.deal_memo.proof_models import ProofFile
from app.modules.deal_memo.record_models import DealRecordEntry
from tests.deal_flow import MEMOS_URL, User, accepted_memo, brand_user, creator_user

GPS_IFD = 0x8825
MAKE, MODEL, ORIENTATION = 0x010F, 0x0110, 0x0112
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def photo(
    fmt: str = "JPEG",
    size: tuple[int, int] = (40, 20),
    *,
    gps: bool = True,
    orientation: int | None = None,
    icc: bytes | None = None,
    text: str | None = None,
) -> bytes:
    """A small image carrying the metadata a real phone photo carries."""
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[MAKE] = "PhoneCo"
    exif[MODEL] = "Model 9 serial 12345"
    if gps:
        # Madurai, to four decimal places: a street, not a city.
        exif[GPS_IFD] = {1: "N", 2: (9.0, 55.0, 24.0), 3: "E", 4: (78.0, 7.0, 12.0)}
    if orientation:
        exif[ORIENTATION] = orientation
    extras: dict = {"exif": exif.tobytes()}
    if icc:
        extras["icc_profile"] = icc
    if fmt == "PNG" and text:
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text("Location", text)
        extras["pnginfo"] = info
    out = io.BytesIO()
    image.save(out, fmt, **extras)
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


# --- the privacy promise, on the images themselves ------------------------------------


@pytest.mark.parametrize(
    ("fmt", "content_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_location_and_camera_details_are_removed(fmt, content_type):
    original = photo(fmt)
    assert opened(original).getexif().get_ifd(GPS_IFD)  # the test photo has GPS

    result = clean_image(original, content_type)

    clean = opened(result.data)
    assert not clean.getexif()  # no EXIF at all: no GPS, no make, no serial
    assert "exif" not in clean.info
    assert clean.format == fmt
    assert result.sha256 == hashlib.sha256(result.data).hexdigest()


def test_png_text_is_removed():
    original = photo("PNG", text="12 Temple Street, Madurai")
    assert "Location" in opened(original).info

    clean = opened(clean_image(original, "image/png").data)

    assert "Location" not in clean.info
    assert not getattr(clean, "text", {})


def test_a_rotated_photo_comes_out_the_right_way_up():
    """The rotation lives in the metadata that is about to be removed, so it
    must be applied to the pixels first, or the photo lands sideways."""
    original = photo(size=(40, 20), orientation=6)  # "rotate 90° to display"

    clean = opened(clean_image(original, "image/jpeg").data)

    assert clean.size == (20, 40)
    assert ORIENTATION not in clean.getexif()


def test_the_colour_profile_is_kept():
    """Not personal, and without it colours shift on some screens."""
    clean = opened(clean_image(photo(icc=SRGB), "image/jpeg").data)

    assert clean.info.get("icc_profile") == SRGB


def test_a_large_photo_is_scaled_to_4096_on_its_longest_side():
    clean = opened(clean_image(photo(size=(5000, 1000), gps=False), "image/jpeg").data)

    assert max(clean.size) == cleaning.MAX_SIDE


def test_a_small_screenshot_keeps_its_size():
    clean = opened(
        clean_image(photo("PNG", size=(1080, 2400), gps=False), "image/png").data
    )

    assert clean.size == (1080, 2400)


# --- what is refused ----------------------------------------------------------------------


def test_a_file_claiming_to_be_a_png_but_holding_a_jpeg_is_refused():
    with pytest.raises(Refused) as refused:
        clean_image(photo("JPEG"), "image/png")
    assert refused.value.reason == "not_an_image"


@pytest.mark.parametrize(
    "data",
    [b"%PDF-1.7 definitely not a picture", b"", photo("JPEG")[:200]],
    ids=["not-an-image", "empty", "truncated"],
)
def test_anything_that_is_not_a_whole_image_is_refused(data):
    with pytest.raises(Refused) as refused:
        clean_image(data, "image/jpeg")
    assert refused.value.reason == "not_an_image"


def test_an_enormous_image_is_refused_before_it_is_decoded():
    """A small file can declare a huge picture; decoding it would exhaust memory."""
    out = io.BytesIO()
    Image.new("1", (8000, 7000)).save(out, "PNG")  # 56 MP, a few kilobytes
    assert len(out.getvalue()) < 100_000

    with pytest.raises(Refused) as refused:
        clean_image(out.getvalue(), "image/png")
    assert refused.value.reason == "too_many_pixels"


# --- the whole path: upload, submit, clean -------------------------------------------------


@pytest.fixture(autouse=True)
def empty_store() -> Iterator[None]:
    storage.memory_store().clear()
    yield
    storage.memory_store().clear()


@pytest.fixture
def deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    return brand, creator, accepted_memo(client, brand, creator)


def upload(
    client, clock, creator: User, memo_id: str, data: bytes, content_type: str
) -> str:
    form = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/uploads",
        json={
            "content_type": content_type,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        headers=creator.headers,
    ).json()
    storage.memory_store().receive(
        form["fields"]["key"], data, content_type=content_type, now=clock.now
    )
    return form["upload_id"]


def submitted(client, clock, creator, memo_id, *files: tuple[bytes, str]) -> list[str]:
    ids = [upload(client, clock, creator, memo_id, data, kind) for data, kind in files]
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"format": "post", "file_ids": ids},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return ids


def test_a_submitted_photo_is_cleaned_and_only_the_clean_copy_is_kept(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    original = photo()
    [file_id] = submitted(client, clock, creator, memo_id, (original, "image/jpeg"))
    incoming_key = db.get(ProofFile, file_id).storage_key
    store = storage.memory_store()

    run = cleaning.clean_attached(db, store, clock.now)

    assert run == cleaning.CleaningRun(cleaned=1, rejected=0, skipped=0)
    row = db.get(ProofFile, file_id)
    db.refresh(row)
    assert row.status == "cleaned"
    assert row.clean_key == f"proof-files/clean/{file_id}.jpg"
    clean_bytes = store.read(row.clean_key, max_bytes=10_000_000)
    assert row.clean_sha256 == hashlib.sha256(clean_bytes).hexdigest()
    assert row.clean_size_bytes == len(clean_bytes)
    assert not opened(clean_bytes).getexif()
    # The original, GPS and all, is gone.
    assert store.describe(incoming_key) is None


def test_the_clean_copys_fingerprint_is_sealed_in_the_deal_record(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    original = photo()
    [file_id] = submitted(client, clock, creator, memo_id, (original, "image/jpeg"))

    cleaning.clean_attached(db, storage.memory_store(), clock.now)

    entry = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == memo_id,
            DealRecordEntry.kind == "proof_file_cleaned",
        )
    ).one()
    row = db.get(ProofFile, file_id)
    assert entry.actor_role == "system"
    assert entry.facts["file_id"] == file_id
    assert entry.facts["sha256"] == hashlib.sha256(original).hexdigest()
    assert entry.facts["clean_sha256"] == row.clean_sha256
    # Sealed after the submission, in order.
    submission = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == memo_id,
            DealRecordEntry.kind == "proof_submitted",
        )
    ).one()
    assert entry.sequence > submission.sequence


def test_a_file_changed_in_storage_after_upload_is_refused_and_removed(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    [file_id] = submitted(client, clock, creator, memo_id, (photo(), "image/jpeg"))
    key = db.get(ProofFile, file_id).storage_key
    store = storage.memory_store()
    store.write(key, photo(gps=False), content_type="image/jpeg")  # swapped bytes

    run = cleaning.clean_attached(db, store, clock.now)

    assert run.rejected == 1
    row = db.get(ProofFile, file_id)
    db.refresh(row)
    assert (row.status, row.rejection_reason) == ("rejected", "fingerprint_mismatch")
    assert store.describe(key) is None


def test_a_file_gone_from_storage_is_refused_as_missing(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = submitted(client, clock, creator, memo_id, (photo(), "image/jpeg"))
    storage.memory_store().delete(db.get(ProofFile, file_id).storage_key)

    cleaning.clean_attached(db, storage.memory_store(), clock.now)

    row = db.get(ProofFile, file_id)
    db.refresh(row)
    assert (row.status, row.rejection_reason) == ("rejected", "missing")


def test_a_non_image_is_refused_and_one_bad_file_never_stops_the_rest(
    client, db, clock, deal
):
    _, creator, memo_id = deal
    good, bad = submitted(
        client,
        clock,
        creator,
        memo_id,
        (photo("PNG"), "image/png"),
        (b"%PDF-1.7 pretending to be a png", "image/png"),
    )

    run = cleaning.clean_attached(db, storage.memory_store(), clock.now)

    assert run == cleaning.CleaningRun(cleaned=1, rejected=1, skipped=0)
    db.expire_all()
    assert db.get(ProofFile, good).status == "cleaned"
    assert db.get(ProofFile, bad).rejection_reason == "not_an_image"


def test_a_second_run_finds_nothing_to_do(client, db, clock, deal):
    _, creator, memo_id = deal
    submitted(client, clock, creator, memo_id, (photo(), "image/jpeg"))
    cleaning.clean_attached(db, storage.memory_store(), clock.now)

    again = cleaning.clean_attached(db, storage.memory_store(), clock.now)

    assert again == cleaning.CleaningRun(cleaned=0, rejected=0, skipped=0)


def test_a_file_no_longer_attached_is_skipped(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = submitted(client, clock, creator, memo_id, (photo(), "image/jpeg"))
    cleaning.clean_attached(db, storage.memory_store(), clock.now)

    assert cleaning.clean_one(db, storage.memory_store(), file_id, clock.now) == "skipped"


def test_pending_uploads_are_never_cleaned(client, db, clock, deal):
    """Only files on a submitted proof are queued; an unused upload is not ours to touch."""
    _, creator, memo_id = deal
    upload(client, clock, creator, memo_id, photo(), "image/jpeg")

    run = cleaning.clean_attached(db, storage.memory_store(), clock.now)

    assert run == cleaning.CleaningRun(cleaned=0, rejected=0, skipped=0)
