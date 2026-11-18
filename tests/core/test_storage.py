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
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.response import StreamingBody
from moto import mock_aws

from app.core import storage
from app.core.deadline import DeadlinePassed
from app.core.storage import (
    MemoryFileStore,
    ObjectTooLarge,
    S3FileStore,
    StorageNotConfigured,
    sha256_base64,
)
from tests.misbehaving_server import misbehaving, timed

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


def test_destroying_removes_every_version_of_that_file_only(s3):
    """D-111: a downloaded export must not survive as an older version."""
    client = s3._client
    client.put_bucket_versioning(
        Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"}
    )
    s3.write("exports/a.json", b"first", content_type="application/json")
    s3.write("exports/a.json", b"second", content_type="application/json")
    s3.write("exports/a.json.other", b"kept", content_type="application/json")
    s3.delete("exports/a.json")
    hidden = client.list_object_versions(Bucket=BUCKET, Prefix="exports/a.json")
    assert any(v["Key"] == "exports/a.json" for v in hidden["Versions"])

    s3.destroy("exports/a.json")

    left = client.list_object_versions(Bucket=BUCKET, Prefix="exports/")
    keys = [v["Key"] for v in left.get("Versions", []) + left.get("DeleteMarkers", [])]
    assert keys == ["exports/a.json.other"]


def test_destroying_what_is_not_there_is_fine(s3):
    s3.destroy("exports/never.json")


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


class _Raw:
    """urllib3's answer as the store reaches it: `read1`, its socket's timeout, `close`.

    Each read returns the next piece and moves `clock` on by `step` seconds;
    every wait the store sets on the socket is kept in `waits`.
    """

    def __init__(self, *pieces: bytes, clock=None, step: float = 0.0) -> None:
        self._pieces = list(pieces)
        self._clock = clock
        self._step = step
        self.closed = False
        self.waits: list[float] = []
        # The path botocore's own `set_socket_timeout` takes to the socket.
        socket = SimpleNamespace(settimeout=self.waits.append)
        self._fp = SimpleNamespace(fp=SimpleNamespace(raw=SimpleNamespace(_sock=socket)))

    def read1(self, amt=None) -> bytes:
        if not self._pieces:
            return b""
        if self._clock is not None:
            self._clock.now += self._step
        return self._pieces.pop(0)

    def close(self) -> None:
        self.closed = True


def _body(raw: _Raw, length: int) -> StreamingBody:
    """botocore's own body over the fake raw stream, as S3's answer carries it."""
    return StreamingBody(raw, length)


class _Events:
    """botocore's event system, as far as the store uses it."""

    def register(self, *args, **kwargs) -> None:
        pass

    def register_first(self, *args, **kwargs) -> None:
        pass


class _FakeClient:
    meta = SimpleNamespace(events=_Events())


class _LyingClient(_FakeClient):
    """Says an object is small, then sends more: the second check must hold."""

    def get_object(self, **kwargs):
        return {"ContentLength": 1, "Body": _body(_Raw(DATA), len(DATA))}


class _SlowBodyClient(_FakeClient):
    """Ten pieces of a file, each taking `step` seconds of `clock`."""

    def __init__(self, clock, step: float) -> None:
        self.raw = _Raw(*([b"x"] * 10), clock=clock, step=step)

    def get_object(self, **kwargs):
        return {"ContentLength": 10, "Body": _body(self.raw, 10)}


class _DeniedClient(_FakeClient):
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


def test_the_stand_in_destroys_a_file(memory):
    memory.write("exports/b.json", b"{}", content_type="application/json")

    memory.destroy("exports/b.json")

    assert memory.describe("exports/b.json") is None


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


# --- a whole limit on every call (item 118, D-186) --------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def timed_s3() -> Iterator[tuple[S3FileStore, Clock, Any]]:
    """The S3 store against moto, on a clock the test moves."""
    clock = Clock()
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        yield S3FileStore(BUCKET, client, clock=clock), clock, client


def test_every_call_is_limited_to_thirty_seconds():
    assert storage.CALL_LIMIT_SECONDS == 30.0


def test_no_try_starts_once_the_call_has_spent_its_limit(timed_s3):
    """botocore asks the hook before every try, its own retries included."""
    store, clock, client = timed_s3
    sent: list[str] = []

    def each_request_takes_31_seconds(**kwargs):
        sent.append(kwargs["request"].method)
        clock.now += 31

    store.write("k", DATA, content_type="image/png")
    # After the store's own hook, so each request is begun in time, then takes 31 s.
    client.meta.events.register("before-send.s3", each_request_takes_31_seconds)
    assert store.describe("k") is not None  # begun in time, so done
    assert sent == ["HEAD"]

    with pytest.raises(DeadlinePassed):
        # The listing takes the limit; no deletion may start after it.
        store.destroy("k")

    assert sent == ["HEAD", "GET"]


def test_no_part_of_an_upload_is_handed_over_once_the_limit_has_passed(timed_s3):
    """An upload whose try began in time but whose body is asked for after the
    limit is refused, not sent: a slow store cannot stretch it (`_SentWithin`)."""
    store, clock, client = timed_s3

    def the_request_takes_31_seconds_before_its_body(**kwargs):
        clock.now += 31

    client.meta.events.register(
        "before-send.s3", the_request_takes_31_seconds_before_its_body
    )
    with pytest.raises(DeadlinePassed):
        store.write("k", DATA, content_type="image/png")

    clock.now = 0.0
    client.meta.events.unregister(
        "before-send.s3", the_request_takes_31_seconds_before_its_body
    )
    assert store.describe("k") is None


def test_a_call_within_its_limit_is_untouched(timed_s3):
    store, _, _ = timed_s3

    store.write("k", DATA, content_type="image/png")

    assert store.read("k", max_bytes=SIZE) == DATA
    store.destroy("k")
    assert store.describe("k") is None


def test_each_call_has_its_own_limit(timed_s3):
    """A limit spent by one call is not inherited by the next."""
    store, clock, _ = timed_s3
    store.write("k", DATA, content_type="image/png")
    clock.now += 1000

    assert store.read("k", max_bytes=SIZE) == DATA


def test_the_limit_hook_is_registered_once_however_many_stores_share_a_client(timed_s3):
    _, _, client = timed_s3
    S3FileStore(BUCKET, client)
    asked: list[int] = []
    original = storage._current_call

    class Counting:
        def get(self):
            asked.append(1)
            return original.get()

        def __getattr__(self, name):
            return getattr(original, name)

    storage._current_call = Counting()
    try:
        client.put_object(Bucket=BUCKET, Key="k", Body=b"x")
    finally:
        storage._current_call = original

    # Once, before the try, though two stores share the client. (The retry
    # hook asks nothing of a try that answered.)
    assert asked == [1]


def test_a_body_still_coming_when_the_limit_passes_is_cut_off():
    """No read begins once the limit is spent: 4 s a piece, 30 s allowed, stops at the eighth."""
    clock = Clock()
    client = _SlowBodyClient(clock, step=4.0)

    with pytest.raises(DeadlinePassed):
        S3FileStore(BUCKET, client, clock=clock).read("k", max_bytes=100)

    assert clock.now == 32.0
    assert client.raw.closed


def test_each_wait_for_the_body_is_cut_to_the_time_the_call_has_left():
    """botocore's 8 s wait until less is left: then 6 s at 24 s, 2 s at 28 s."""
    clock = Clock()
    client = _SlowBodyClient(clock, step=4.0)

    with pytest.raises(DeadlinePassed):
        S3FileStore(BUCKET, client, clock=clock).read("k", max_bytes=100)

    assert client.raw.waits == [8.0] * 6 + [6.0, 2.0]


def test_a_body_read_in_time_is_returned_and_closed():
    clock = Clock()
    client = _SlowBodyClient(clock, step=1.0)

    assert S3FileStore(BUCKET, client, clock=clock).read("k", max_bytes=10) == b"x" * 10
    assert client.raw.closed


def test_botocore_still_checks_the_bodys_length():
    """The body is botocore's own: one that ends short of its announced length is refused."""
    from botocore.exceptions import IncompleteReadError

    class ShortClient(_FakeClient):
        def get_object(self, **kwargs):
            return {"ContentLength": 10, "Body": _body(_Raw(b"x" * 4), 10)}

    with pytest.raises(IncompleteReadError):
        S3FileStore(BUCKET, ShortClient()).read("k", max_bytes=100)


# --- the real thing, on a real socket ---------------------------------------------------


def s3_at(url: str, read_timeout: float = storage.READ_WAIT_SECONDS) -> Any:
    from botocore.config import Config

    return boto3.client(
        "s3",
        region_name="ap-south-1",
        endpoint_url=url,
        aws_access_key_id="test-key-not-real",
        aws_secret_access_key="test-secret-not-real",
        config=Config(
            connect_timeout=storage.CONNECT_WAIT_SECONDS,
            read_timeout=read_timeout,
            retries={"mode": "standard", "total_max_attempts": storage.TRIES},
        ),
    )


LIMIT = 1.0
# How far past its limit a call may end: the time to notice, never a wait.
SLACK = 0.25


@pytest.mark.parametrize("gap", [0.2, 0.03, 0.01])
def test_a_body_trickled_at_any_rate_is_cut_off_at_the_limit(monkeypatch, gap):
    """Each byte inside botocore's 10 s read wait, at any rate: a read that
    waited for its whole piece would run 64 KiB times the gap (11 minutes at
    0.01 s); one socket read at a time ends at the limit."""
    monkeypatch.setattr(storage, "CALL_LIMIT_SECONDS", LIMIT)
    with misbehaving("trickle_body", content_type="image/png", gap=gap) as server:
        store = S3FileStore(BUCKET, s3_at(server.url))
        outcome, elapsed = timed(lambda: store.read("k", max_bytes=20_000_000))

    assert isinstance(outcome, DeadlinePassed), outcome
    assert len(server.requests) == 1
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


def test_a_body_that_stops_coming_is_cut_off_at_the_limit(monkeypatch):
    """Headers, then silence: the wait for the body is cut to the time left,
    not botocore's 10 s."""
    monkeypatch.setattr(storage, "CALL_LIMIT_SECONDS", LIMIT)
    with misbehaving("silent_body", content_type="image/png") as server:
        store = S3FileStore(BUCKET, s3_at(server.url))
        outcome, elapsed = timed(lambda: store.read("k", max_bytes=20_000_000))

    assert isinstance(outcome, DeadlinePassed), outcome
    assert len(server.requests) == 1
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


UPLOAD_LIMIT = 4.0
UPLOAD_WAIT = 1.0


@pytest.fixture
def pauses(monkeypatch) -> list[float]:
    """Every pause botocore takes between tries, still taken for real.

    botocore sleeps in one place, `botocore.endpoint`, before a retry.
    """
    import time

    import botocore.endpoint

    taken: list[float] = []

    class _Time:
        def __getattr__(self, name: str) -> Any:
            return getattr(time, name)

        def sleep(self, seconds: float) -> None:
            taken.append(seconds)
            time.sleep(seconds)

    monkeypatch.setattr(botocore.endpoint, "time", _Time())
    return taken


def test_an_upload_read_slowly_ends_within_the_limit(monkeypatch, pauses):
    """A store reading 16 KiB every 0.05 s would take 26 s over 8 MiB, each
    send inside the socket's 1 s wait. Its parts, as traced on 15 November
    2026: botocore waits up to 1 s for "100 Continue", then sends 128 KiB
    blocks, each send held to the socket's wait (1 s here). A block is handed
    over only while its send and the wait for the answer after it (2 x 1 s)
    still fit, and botocore never pauses for a retry once an upload has been
    stopped, so the call ends before its 4 s limit: by its own parts, no later
    than 4 - 2 + 1 = 3 s, plus the time to notice."""
    monkeypatch.setattr(storage, "CALL_LIMIT_SECONDS", UPLOAD_LIMIT)
    monkeypatch.setattr(storage, "READ_WAIT_SECONDS", UPLOAD_WAIT)
    data = b"x" * (8 * 1024 * 1024)
    with misbehaving(
        "slow_reader", receive_buffer=4096, gap=0.05, read_bytes=16384
    ) as server:
        store = S3FileStore(BUCKET, s3_at(server.url, read_timeout=UPLOAD_WAIT))
        outcome, elapsed = timed(lambda: store.write("k", data, content_type="image/png"))

    assert isinstance(outcome, DeadlinePassed), outcome
    # One try only: no retry is begun, or paused for, once the upload stopped
    # (botocore sees the refused block as a closed connection, which it would
    # otherwise pause for and try again).
    assert server.connections == 1
    assert pauses == []
    assert 0 < server.received < len(data)
    assert elapsed < UPLOAD_LIMIT


def test_a_try_that_fails_after_the_limit_is_not_paused_for(pauses):
    """S3 answers 500 once the call's limit has passed: botocore would pause
    before its second try, only for that try to be refused. It is stopped
    before the pause instead, and the store is asked once."""
    clock = Clock()
    with misbehaving("flaky", body=DATA, content_type="image/png") as server:
        client = s3_at(server.url)
        store = S3FileStore(BUCKET, client, clock=clock)

        def the_try_outlasts_the_limit(**kwargs):
            clock.now = storage.CALL_LIMIT_SECONDS + 1

        # After the store's own hook, so the try is begun in time.
        client.meta.events.register("before-send.s3", the_try_outlasts_the_limit)
        outcome, _ = timed(lambda: store.read("k", max_bytes=SIZE))

    assert isinstance(outcome, DeadlinePassed), outcome
    assert len(server.requests) == 1
    assert pauses == []


def test_a_try_that_fails_in_time_is_tried_again(pauses):
    """The same 500 with time left: botocore's own pause and second try."""
    with misbehaving("flaky", body=DATA, content_type="image/png") as server:
        store = S3FileStore(BUCKET, s3_at(server.url), clock=Clock())
        outcome, _ = timed(lambda: store.read("k", max_bytes=SIZE))

    assert outcome == DATA
    assert len(server.requests) == 2
    assert len(pauses) == 1


def test_an_upload_never_hands_over_a_block_it_could_not_finish_in_time(timed_s3):
    """With less left than a block's send and the answer's wait (2 x 8 s), the
    next block is refused, and the call is marked stopped so botocore does not
    pause to try it again."""
    store, clock, client = timed_s3

    def the_request_leaves_fifteen_seconds(**kwargs):
        clock.now = storage.CALL_LIMIT_SECONDS - 15.0

    client.meta.events.register("before-send.s3", the_request_leaves_fifteen_seconds)
    with pytest.raises(DeadlinePassed):
        store.write("k", DATA, content_type="image/png")
    client.meta.events.unregister("before-send.s3", the_request_leaves_fifteen_seconds)
    clock.now = 0.0

    assert store.describe("k") is None


def test_an_upload_with_time_for_its_blocks_is_sent(timed_s3):
    """Seventeen seconds left is a block's send and its answer's wait, and more."""
    store, clock, client = timed_s3

    def the_request_leaves_seventeen_seconds(**kwargs):
        clock.now = storage.CALL_LIMIT_SECONDS - 17.0

    client.meta.events.register("before-send.s3", the_request_leaves_seventeen_seconds)
    store.write("k", DATA, content_type="image/png")
    client.meta.events.unregister("before-send.s3", the_request_leaves_seventeen_seconds)

    assert store.read("k", max_bytes=SIZE) == DATA


def test_the_client_is_configured_so_one_request_ends_within_the_limit():
    """Adhi's decision of 15 November 2026: the worst case of one request,
    computed from the client's own configuration and botocore's own backoff,
    every try's connect and wait for an answer and every pause between them,
    is under the call's limit."""
    config = storage.s3_client().meta.config

    assert config.retries == {"mode": "standard", "total_max_attempts": 2}
    worst = storage.worst_request_seconds(
        config.connect_timeout,
        config.read_timeout,
        config.retries["total_max_attempts"],
    )
    assert worst == 2 * (3 + 8) + 1 + 5 == 28
    assert worst < storage.CALL_LIMIT_SECONDS


def test_the_worst_case_counts_every_pause_botocore_may_take():
    """One try: no pause. Three: 1 s, then 2 s, each with 5 s more for a store
    that asks with `x-amz-retry-after`; the pause is capped at 20 s."""
    assert storage.worst_request_seconds(3, 8, 1) == 11
    assert storage.worst_request_seconds(3, 8, 3) == 33 + (1 + 5) + (2 + 5)
    assert storage.worst_request_seconds(0, 0, 7) == sum(
        min(2**n, 20) + 5 for n in range(6)
    )


def test_a_store_that_never_answers_ends_within_the_limit(monkeypatch):
    """Both tries wait their whole 0.4 s for an answer that never comes, and
    the pause between them is botocore's, at most 1 s: by its parts the call
    ends by 0.4 + 1 + 0.4 = 1.8 s, inside its 2.5 s limit, and the second try
    is always begun in time, so it is botocore's own timeout that ends it."""
    monkeypatch.setattr(storage, "CALL_LIMIT_SECONDS", 2.5)
    with misbehaving("silent") as server:
        store = S3FileStore(BUCKET, s3_at(server.url, read_timeout=0.4))
        outcome, elapsed = timed(lambda: store.read("k", max_bytes=100))

    assert isinstance(outcome, ReadTimeoutError), outcome
    assert len(server.requests) == 2
    assert elapsed < 2.5


def test_a_destroy_starts_no_request_whose_worst_case_no_longer_fits(timed_s3):
    """A listing that leaves 27 s: one more request could take 28 s, so the
    deletion is not begun, and the file waits for the next run."""
    store, clock, client = timed_s3
    store.write("k", DATA, content_type="image/png")

    def the_listing_takes_three_seconds(**kwargs):
        if kwargs["request"].method == "GET":
            clock.now += 3.0

    client.meta.events.register("before-send.s3", the_listing_takes_three_seconds)
    with pytest.raises(DeadlinePassed):
        store.destroy("k")
    client.meta.events.unregister("before-send.s3", the_listing_takes_three_seconds)

    assert store.describe("k") is not None


def test_a_destroy_with_time_left_deletes_every_version(timed_s3):
    store, clock, client = timed_s3
    store.write("k", DATA, content_type="image/png")

    def the_listing_takes_one_second(**kwargs):
        if kwargs["request"].method == "GET":
            clock.now += 1.0

    client.meta.events.register("before-send.s3", the_listing_takes_one_second)
    store.destroy("k")
    client.meta.events.unregister("before-send.s3", the_listing_takes_one_second)

    assert store.describe("k") is None


class _Stream:
    """A body arriving in pieces, one socket read each."""

    def __init__(self, *pieces: bytes) -> None:
        self.pieces = list(pieces)
        self.asked: list[int] = []

    def read1(self, amt):
        self.asked.append(amt)
        return self.pieces.pop(0) if self.pieces else b""


def test_reading_the_rest_of_a_body_reads_until_it_ends():
    """`read()` with no size means all of it: every piece, never just the first."""
    from app.core.deadline import Deadline

    stream = _Stream(b"ab", b"cd", b"e")

    assert storage._OneWaitAtATime(stream, Deadline(30)).read() == b"abcde"
    assert stream.asked == [storage.READ_PIECE_BYTES] * 4


def test_reading_a_size_is_one_socket_read():
    from app.core.deadline import Deadline

    stream = _Stream(b"ab", b"cd")

    assert storage._OneWaitAtATime(stream, Deadline(30)).read(10) == b"ab"
    assert stream.asked == [10]


def test_a_store_that_fails_once_then_answers_is_read():
    with misbehaving("flaky", body=DATA, content_type="image/png") as server:
        store = S3FileStore(BUCKET, s3_at(server.url))
        outcome, elapsed = timed(lambda: store.read("k", max_bytes=SIZE))

    assert outcome == DATA
    assert len(server.requests) == 2
    assert elapsed < storage.CALL_LIMIT_SECONDS
