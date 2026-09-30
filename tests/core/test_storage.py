"""The storage seam (D-065): the S3 store against moto, and the stand-in's rules.

moto imitates S3 inside the process, so these run without AWS or a network.
What moto cannot show is S3 itself refusing a mismatched upload; that is why
the signed form is checked here field by field, and why the stand-in refuses
exactly what the form tells S3 to refuse.
"""

import base64
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from moto import mock_aws

from app.core import storage
from app.core.storage import (
    MemoryFileStore,
    ObjectTooLarge,
    S3FileStore,
    StorageNotConfigured,
    sha256_base64,
)

BUCKET = "colyv-test-uploads"
NOW = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
DATA = b"\x89PNG\r\n\x1a\n not really a png, which is fine here"
SHA = hashlib.sha256(DATA).hexdigest()
SIZE = len(DATA)


@pytest.fixture
def s3() -> Iterator[S3FileStore]:
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        yield S3FileStore(BUCKET, client)


def policy_of(form) -> dict:
    return json.loads(base64.b64decode(form.fields["policy"]))


# --- the S3 store -------------------------------------------------------------------


def test_the_upload_form_pins_size_type_and_fingerprint(s3):
    form = s3.upload_form(
        "proof-files/incoming/a",
        content_type="image/png",
        size=len(DATA),
        sha256_hex=SHA,
        expires_in=timedelta(minutes=10),
        now=NOW,
    )

    conditions = policy_of(form)["conditions"]
    assert {"Content-Type": "image/png"} in conditions
    assert {"x-amz-checksum-algorithm": "SHA256"} in conditions
    assert {"x-amz-checksum-sha256": sha256_base64(SHA)} in conditions
    # Exactly the declared size: one value, not a range to fill.
    assert ["content-length-range", len(DATA), len(DATA)] in conditions
    assert {"key": "proof-files/incoming/a"} in conditions
    assert form.fields["key"] == "proof-files/incoming/a"
    assert form.expires_at == NOW + timedelta(minutes=10)


def test_the_form_expires_when_it_says(s3):
    form = s3.upload_form(
        "k",
        content_type="image/png",
        size=1,
        sha256_hex=SHA,
        expires_in=timedelta(minutes=10),
        now=NOW,
    )

    expiration = datetime.fromisoformat(
        policy_of(form)["expiration"].replace("Z", "+00:00")
    )
    # Signed against the real clock, so within a few minutes of now + 10.
    assert timedelta(minutes=9) < expiration - datetime.now(UTC) <= timedelta(minutes=10)


def test_a_missing_object_is_described_as_none(s3):
    assert s3.describe("nothing/here") is None


def test_write_describe_read_and_delete(s3):
    s3.write("proof-files/clean/a.png", DATA, content_type="image/png")

    assert s3.describe("proof-files/clean/a.png") == storage.StoredObject(
        size=len(DATA), content_type="image/png"
    )
    assert s3.read("proof-files/clean/a.png", max_bytes=1024) == DATA

    s3.delete("proof-files/clean/a.png")
    assert s3.describe("proof-files/clean/a.png") is None


def test_reading_more_than_agreed_is_refused(s3):
    s3.write("big", DATA, content_type="image/png")

    with pytest.raises(ObjectTooLarge):
        s3.read("big", max_bytes=len(DATA) - 1)


def test_a_view_link_is_signed_short_lived_and_names_the_file(s3):
    url = s3.view_url(
        "proof-files/clean/a.png", expires_in=timedelta(minutes=5), filename="p.png"
    )

    query = parse_qs(urlparse(url).query)
    assert query["X-Amz-Expires"] == ["300"]
    assert "X-Amz-Signature" in query
    assert query["response-content-disposition"] == ['inline; filename="p.png"']


def test_the_fingerprint_is_sent_as_s3_wants_it():
    assert sha256_base64(SHA) == base64.b64encode(hashlib.sha256(DATA).digest()).decode()


# --- the stand-in --------------------------------------------------------------------


@pytest.fixture
def memory() -> MemoryFileStore:
    return MemoryFileStore()


def form_for(memory, key="k", *, size=SIZE, sha=SHA, content_type="image/png"):
    return memory.upload_form(
        key,
        content_type=content_type,
        size=size,
        sha256_hex=sha,
        expires_in=timedelta(minutes=10),
        now=NOW,
    )


def test_the_stand_in_accepts_exactly_the_declared_file(memory):
    form_for(memory)

    memory.receive("k", DATA, content_type="image/png", now=NOW)

    assert memory.describe("k") == storage.StoredObject(
        size=len(DATA), content_type="image/png"
    )


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (DATA + b"!", "image/png"),  # a different size
        (DATA, "image/jpeg"),  # a different type
        (bytes(reversed(DATA)), "image/png"),  # same size, different bytes
    ],
)
def test_the_stand_in_refuses_what_s3_would_refuse(memory, data, content_type):
    form_for(memory)

    with pytest.raises(PermissionError):
        memory.receive("k", data, content_type=content_type, now=NOW)
    assert memory.describe("k") is None


def test_an_expired_form_is_refused(memory):
    form_for(memory)

    with pytest.raises(PermissionError):
        memory.receive(
            "k", DATA, content_type="image/png", now=NOW + timedelta(minutes=10)
        )


def test_an_upload_without_a_form_is_refused(memory):
    with pytest.raises(PermissionError):
        memory.receive("k", DATA, content_type="image/png", now=NOW)


def test_the_stand_in_reads_writes_and_deletes(memory):
    memory.write("x", DATA, content_type="image/png")
    assert memory.read("x", max_bytes=1024) == DATA
    with pytest.raises(ObjectTooLarge):
        memory.read("x", max_bytes=1)

    memory.delete("x")
    assert memory.describe("x") is None
    assert memory.keys() == set()


# --- which store -------------------------------------------------------------------


def test_with_a_bucket_the_store_is_s3(monkeypatch):
    monkeypatch.setattr(storage.settings, "uploads_bucket", BUCKET)
    monkeypatch.setattr(storage, "_s3_store", None)
    with mock_aws():
        store = storage.get_file_store()

    assert isinstance(store, S3FileStore)
    assert store.bucket == BUCKET


def test_without_a_bucket_tests_get_the_stand_in(monkeypatch):
    monkeypatch.setattr(storage.settings, "uploads_bucket", None)

    assert storage.get_file_store() is storage.memory_store()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_without_a_bucket_a_real_deployment_refuses(monkeypatch, environment):
    """Never keep somebody's proof in one process's memory by mistake."""
    monkeypatch.setattr(storage.settings, "uploads_bucket", None)
    monkeypatch.setattr(storage.settings, "environment", environment)

    with pytest.raises(StorageNotConfigured):
        storage.get_file_store()


# --- the edges --------------------------------------------------------------------------


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amount: int) -> bytes:
        return self._data[:amount]

    def close(self) -> None:
        pass


class _LyingClient:
    """Says an object is small, then sends more: the second check must hold."""

    def get_object(self, **kwargs):
        return {"ContentLength": 1, "Body": _Body(DATA)}


class _DeniedClient:
    def head_object(self, **kwargs):
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")


def test_a_body_longer_than_s3_announced_is_still_refused():
    with pytest.raises(ObjectTooLarge):
        S3FileStore(BUCKET, _LyingClient()).read("k", max_bytes=SIZE - 1)


def test_access_denied_is_raised_never_taken_for_a_missing_file():
    """A permissions fault read as "not there" would make a proof look unsent."""
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError):
        S3FileStore(BUCKET, _DeniedClient()).describe("k")


def test_the_stand_in_says_so_when_a_file_is_missing(memory):
    with pytest.raises(KeyError):
        memory.read("nothing", max_bytes=10)


def test_the_stand_in_names_its_view_links_and_can_be_cleared(memory):
    form_for(memory)
    memory.receive("k", DATA, content_type="image/png", now=NOW)

    url = memory.view_url("k", expires_in=timedelta(minutes=5), filename="p.png")
    assert "filename=p.png" in url and "expires=300" in url

    memory.clear()
    assert memory.keys() == set()
    with pytest.raises(PermissionError):
        memory.receive("k", DATA, content_type="image/png", now=NOW)


def test_the_s3_store_is_made_once_and_reused(monkeypatch):
    monkeypatch.setattr(storage.settings, "uploads_bucket", BUCKET)
    monkeypatch.setattr(storage, "_s3_store", None)
    with mock_aws():
        assert storage.get_file_store() is storage.get_file_store()
