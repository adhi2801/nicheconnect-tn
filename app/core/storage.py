"""Private file storage (D-065): S3 in AWS, an in-memory stand-in elsewhere.

One seam, like the embedder's and the OTP sender's, so the rules that use it
are tested without AWS and without a network.

**Files never pass through our server on the way in.** The phone uploads
straight to S3 with a signed form (D-062), and the form carries the rules S3
enforces itself: exactly the declared size, the declared type, and the
declared SHA-256 fingerprint. A different file is refused by S3 before we
ever see it. What we store afterwards is checked again on our side
(`describe`, and the cleaning job's own hash of the bytes), so nothing rests
on one check alone.

**Nothing is public.** Reading is only through a link signed for a few
minutes, for one object.

**Every call to S3 ends within CALL_LIMIT_SECONDS** (item 118, D-186;
Adhi's decision of 15 November 2026, "bound it by config"). botocore bounds
each wait and its tries, never their sum, so the client is configured for a
sum that fits: 2 tries in all, each connect at most 3 s and each wait for
bytes at most 8 s, and botocore's longest pause between them 1 s, or 6 s
when S3 asks with `x-amz-retry-after`. One request that never answers
therefore ends within 2 x (3 + 8) + 6 = 28 s (`worst_request_seconds`,
computed from the client's own configuration by a test), for a name that
resolves to one address: urllib3 tries each address with the whole 3 s
connect, so each unreachable one adds 3 s (D-186 point 14, a gap awaiting
a decision). On top of that,
each call carries one `Deadline`:

- botocore asks `_refuse_late_try` before every try, retries included, and
  none starts once the limit has passed; `_no_retry_past_the_limit` stops
  botocore before its pause once the limit has passed or an upload was
  stopped, so no pause is spent on a try that would be refused;
- a file's body is read one socket read at a time (`_OneWaitAtATime`), each
  wait cut to the time the call has left, so a body trickled at any rate
  ends at the limit; botocore's own checks on the body (its length, and its
  checksum when S3 sends one) still run;
- an upload's next block is handed over only while a block's send and the
  wait for the answer after it (2 x 8 s) still fit (`_SentWithin`), so an
  upload ends within the limit;
- a destroy starts each further request only while a whole request's worst
  case still fits.

**The one gap, accepted in writing by Adhi on 15 November 2026:** a store
that trickles its answer's headers a byte at a time, each inside the 8 s
wait, is not cut off, since botocore offers no hook on that socket. Only a
hostile server does this, and ours is AWS's S3 itself, over TLS, in the
same region. Measured on 18 November 2026 with this configuration and the
30 s limit, a store that never answers ended within 17.0 s, the worst of 3
runs (16.4 to 17.0 s: two tries of 8 s and botocore's pause between them;
connecting locally takes no time).
"""

import base64
import hashlib
import io
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, Protocol

from app.core.config import settings
from app.core.deadline import Clock, Deadline, DeadlinePassed
from app.core.errors import DomainError

# Outside AWS nothing is uploaded for real, so the stand-in is only allowed
# where nobody's files are at stake.
MEMORY_STORE_ENVIRONMENTS = frozenset({"local", "test"})
# One call to the store, every try and wait included, a file's whole body
# among them (item 118, D-186): a 7 MB proof read in AWS's own region takes
# well under a second, so 30 s is a stuck store, not a slow one.
CALL_LIMIT_SECONDS = 30.0
# The most one socket read may return; a read returns what has arrived.
READ_PIECE_BYTES = 64 * 1024
# botocore's own waits (`s3_client`): a connect, and the wait for the next
# bytes, which is also the longest one read of a body, or one send of an
# upload's block, may wait.
CONNECT_WAIT_SECONDS = 3.0
READ_WAIT_SECONDS = 8.0
# botocore's tries in all, the first included (`total_max_attempts`).
TRIES = 2
# Registered once per client, however many stores share it.
_HOOK_ID = "colyv-call-limit"
_RETRY_HOOK_ID = "colyv-call-limit-retry"
# The codes S3 answers for an object that is not there: HEAD has no body,
# so only its status; GET names it.
_NOT_FOUND = frozenset({"404", "NoSuchKey", "NotFound"})


@dataclass
class _Call:
    """One call's limit, and whether an upload of it was stopped."""

    deadline: Deadline
    stopped: bool = False


_current_call: ContextVar[_Call | None] = ContextVar("storage_call", default=None)


def worst_request_seconds(connect: float, read: float, tries: int) -> float:
    """The longest one botocore request can take, every try and pause included.

    Each try: its connect and one wait for the answer. Between tries,
    botocore's standard retry mode pauses at most `min(2 ** (n - 1), 20)`
    seconds before try n + 1, and up to 5 s more when the store asks with
    `x-amz-retry-after` (botocore.retries.standard.ExponentialBackoff, read
    from the installed botocore, never copied).
    """
    from botocore.retries.standard import ExponentialBackoff as Backoff

    pauses = sum(
        min(Backoff._BASE ** (n - 1), Backoff._MAX_BACKOFF)
        + Backoff._RETRY_AFTER_MAX_ADDITIONAL
        for n in range(1, tries)
    )
    return float(tries * (connect + read) + pauses)


def _refuse_late_try(**_: Any) -> None:
    """botocore's `before-send` event, before every try: none once the limit has passed."""
    call = _current_call.get()
    if call is not None and call.deadline.expired():
        raise DeadlinePassed("a storage call passed its limit")


def _no_retry_past_the_limit(
    response: Any = None, caught_exception: Exception | None = None, **_: Any
) -> None:
    """botocore's `needs-retry` event, asked after every try, before any pause.

    Registered first, so it is asked before botocore's own retry handler. A
    try that answered (below 400) is never a retry, and its answer stands
    however late it came. A failed one, once the limit has passed or an upload
    was stopped for want of time, has no try left to pause for.
    """
    if (
        caught_exception is None
        and response is not None
        and response[0].status_code < 400
    ):
        return
    call = _current_call.get()
    if call is not None and (call.stopped or call.deadline.expired()):
        raise DeadlinePassed("a storage call passed its limit")


class _OneWaitAtATime:
    """urllib3's answer under botocore's body, read one socket read at a time.

    urllib3's `read(n)` waits until it has all `n` bytes, each socket wait
    inside the read timeout, so a body trickled a byte every few
    milliseconds never times out. `read1` returns after one socket read, and
    each one's wait is cut to the time the call has left, so no read of the
    body ends later than the limit. Given to botocore's `StreamingBody` in
    place of its raw stream, so botocore still counts the body's length and
    checks its checksum.
    """

    def __init__(self, raw: Any, deadline: Deadline) -> None:
        self._raw = raw
        self._deadline = deadline

    def read(self, amt: int | None = None) -> bytes:
        """At most `amt` bytes from one socket read; with no `amt`, all of the rest.

        All of the rest is read one cut wait at a time, until the stream ends,
        so it is never one socket read mistaken for the whole body.
        """
        if amt is None:
            pieces: list[bytes] = []
            while piece := self._read_once(READ_PIECE_BYTES):
                pieces.append(piece)
            return b"".join(pieces)
        return self._read_once(amt)

    def _read_once(self, amt: int) -> bytes:
        from botocore.compat import set_socket_timeout
        from urllib3.exceptions import ReadTimeoutError

        left = self._deadline.remaining()
        if left <= 0:
            raise DeadlinePassed("reading a stored file passed its limit")
        wait = min(READ_WAIT_SECONDS, left)
        # botocore's own way to the socket (`StreamingBody.set_socket_timeout`).
        # There is none once http.client has read the whole body and let the
        # socket go, nor under an answer made in memory (moto's); then the
        # read cannot wait. Were the way ever to change, the real-socket tests
        # (`tests/core/test_storage.py`) would fail, not pass by luck.
        with suppress(AttributeError):
            set_socket_timeout(self._raw, wait)
        try:
            piece: bytes = self._raw.read1(amt)
        except ReadTimeoutError as error:
            if wait < READ_WAIT_SECONDS:
                # The wait was what the call had left: the limit ended it.
                raise DeadlinePassed("reading a stored file passed its limit") from error
            raise
        return piece

    def close(self) -> None:
        self._raw.close()


class _SentWithin(io.BytesIO):
    """An upload's bytes, handed to the socket only while there is time to send them.

    The HTTP layer sends a body read from a file one block at a time (128 KiB
    under botocore 1.43), each block's send bounded by the socket's own wait
    (READ_WAIT_SECONDS, total for the send); after the last block it waits
    up to as long again for the answer's first bytes. A block is therefore
    handed over only while both waits still fit in what the call has left
    (`keep_back`); once they do not, this refuses and marks the call stopped,
    so an upload ends within the limit and botocore does not pause to try it
    again (`_no_retry_past_the_limit`). Measured on 15 November 2026: before
    this, the last block's send and botocore's pause before a refused retry
    ran up to 1.9 s past a 2 s limit on GitHub's runner.
    """

    def __init__(self, data: bytes, call: _Call, keep_back: float) -> None:
        super().__init__(data)
        self._call = call
        self._keep_back = keep_back

    def read(self, size: int | None = -1) -> bytes:
        if self._call.deadline.remaining() < self._keep_back:
            self._call.stopped = True
            raise DeadlinePassed("sending a file to storage passed its limit")
        return super().read(size)


def storage_failures() -> tuple[type[Exception], ...]:
    """Every way a call to the store can fail without the file being at fault.

    The call's limit passing, and botocore's own failures: a timeout, no
    connection, a refusal from S3 (`ClientError`). A job catches these to
    leave one item due and go on with the rest.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    return (DeadlinePassed, BotoCoreError, ClientError)


class StorageNotConfigured(DomainError):
    """No bucket is set in an environment that must have one.

    A 503 in the one error format: uploads are unavailable on this server,
    which is ours to fix, not the person's.
    """

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "uploads_unavailable"
    title = "File uploads are not available right now"


class ObjectTooLarge(ValueError):
    """An object is larger than the caller agreed to read."""


@dataclass(frozen=True)
class UploadForm:
    """Where and how the phone uploads one file: a POST of `fields` + the file."""

    url: str
    fields: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True)
class StoredObject:
    size: int
    content_type: str | None


class FileStore(Protocol):
    """What the rest of the app may do with stored files, and nothing more."""

    def upload_form(
        self,
        key: str,
        *,
        content_type: str,
        size: int,
        sha256_hex: str,
        expires_in: timedelta,
        now: datetime,
    ) -> UploadForm: ...

    def describe(self, key: str) -> StoredObject | None: ...

    def read(self, key: str, *, max_bytes: int) -> bytes: ...

    def write(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def destroy(self, key: str) -> None:
        """Delete the object and every earlier version of it, beyond recovery."""
        ...

    def view_url(self, key: str, *, expires_in: timedelta, filename: str) -> str: ...


def sha256_base64(sha256_hex: str) -> str:
    """S3 wants the fingerprint as base64 of the raw digest, not as hex."""
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")


# --- S3 -----------------------------------------------------------------------


class S3FileStore:
    """The real store: one private bucket, reached with the task's own role."""

    def __init__(self, bucket: str, client: Any, clock: Clock = time.monotonic) -> None:
        self.bucket = bucket
        self._client = client
        self._clock = clock
        client.meta.events.register(
            "before-send.s3", _refuse_late_try, unique_id=_HOOK_ID
        )
        client.meta.events.register_first(
            "needs-retry.s3", _no_retry_past_the_limit, unique_id=_RETRY_HOOK_ID
        )

    @contextmanager
    def _call(self) -> Iterator[_Call]:
        """One call's limit, seen by every try botocore makes inside the block."""
        call = _Call(Deadline(CALL_LIMIT_SECONDS, self._clock))
        token = _current_call.set(call)
        try:
            yield call
        finally:
            _current_call.reset(token)

    def upload_form(
        self,
        key: str,
        *,
        content_type: str,
        size: int,
        sha256_hex: str,
        expires_in: timedelta,
        now: datetime,
    ) -> UploadForm:
        checksum = sha256_base64(sha256_hex)
        fields = {
            "Content-Type": content_type,
            "x-amz-checksum-algorithm": "SHA256",
            "x-amz-checksum-sha256": checksum,
        }
        # Every field is also a condition, so none can be changed on the
        # phone; the size range is a single value, the declared one.
        conditions: list[Any] = [
            {"Content-Type": content_type},
            {"x-amz-checksum-algorithm": "SHA256"},
            {"x-amz-checksum-sha256": checksum},
            ["content-length-range", size, size],
        ]
        signed = self._client.generate_presigned_post(
            Bucket=self.bucket,
            Key=key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return UploadForm(
            url=signed["url"],
            fields={name: str(value) for name, value in signed["fields"].items()},
            expires_at=now + expires_in,
        )

    def describe(self, key: str) -> StoredObject | None:
        from botocore.exceptions import ClientError

        try:
            with self._call():
                head = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _NOT_FOUND:
                return None
            raise
        return StoredObject(
            size=int(head["ContentLength"]), content_type=head.get("ContentType")
        )

    def read(self, key: str, *, max_bytes: int) -> bytes:
        """The file, read one socket read at a time within CALL_LIMIT_SECONDS.

        Raises KeyError when there is no such object (as the stand-in does),
        ObjectTooLarge, or DeadlinePassed once the limit is spent.
        """
        from botocore.exceptions import ClientError

        with self._call() as call:
            try:
                response = self._client.get_object(Bucket=self.bucket, Key=key)
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") in _NOT_FOUND:
                    raise KeyError(key) from error
                raise
            body = response["Body"]
            try:
                if int(response["ContentLength"]) > max_bytes:
                    raise ObjectTooLarge(key)
                # The one seam botocore leaves: the stream its body reads from.
                body._raw_stream = _OneWaitAtATime(body._raw_stream, call.deadline)
                data = bytearray()
                for piece in body.iter_chunks(chunk_size=READ_PIECE_BYTES):
                    data += piece
                    if len(data) > max_bytes:
                        raise ObjectTooLarge(key)
                return bytes(data)
            finally:
                body.close()

    def write(self, key: str, data: bytes, *, content_type: str) -> None:
        with self._call() as call:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=_SentWithin(data, call, keep_back=2 * READ_WAIT_SECONDS),
                ContentType=content_type,
                ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode(
                    "ascii"
                ),
            )

    def delete(self, key: str) -> None:
        with self._call():
            self._client.delete_object(Bucket=self.bucket, Key=key)

    def destroy(self, key: str) -> None:
        # The bucket keeps versions, so a plain delete only hides an object
        # for a month (`tidy`). Deleting each version by its id removes it.
        # One limit for the listing and every deletion: a destroy that stops
        # halfway is asked again by its job's next run. Each further request
        # starts only while its whole worst case still fits.
        with self._call() as call:
            listed = self._client.list_object_versions(Bucket=self.bucket, Prefix=key)
            for entry in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]:
                if entry["Key"] == key:
                    if call.deadline.remaining() < worst_request_seconds(
                        CONNECT_WAIT_SECONDS, READ_WAIT_SECONDS, TRIES
                    ):
                        raise DeadlinePassed("destroying a stored file passed its limit")
                    self._client.delete_object(
                        Bucket=self.bucket, Key=key, VersionId=entry["VersionId"]
                    )

    def view_url(self, key: str, *, expires_in: timedelta, filename: str) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                # Shown in the browser, under a name that says what it is.
                "ResponseContentDisposition": f'inline; filename="{filename}"',
            },
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return url


def s3_client() -> Any:
    """A client with short timeouts and AWS's standard retries with backoff.

    CLAUDE.md section 3: an external call retries with backoff and never
    hangs a request. Credentials come from the task's role; none are ever
    in our settings.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(
            signature_version="s3v4",
            connect_timeout=CONNECT_WAIT_SECONDS,
            read_timeout=READ_WAIT_SECONDS,
            retries={"mode": "standard", "total_max_attempts": TRIES},
        ),
    )


# --- the stand-in -------------------------------------------------------------


class MemoryFileStore:
    """Keeps files in a dict, and enforces what S3's signed form enforces.

    `receive` plays the phone's upload: it refuses exactly what S3 would
    refuse (wrong size, type or fingerprint, or an expired form), so the
    rules around uploads can be tested end to end without AWS.
    """

    URL = "https://uploads.invalid/memory"

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._forms: dict[str, tuple[str, int, str, datetime]] = {}
        self._lock = threading.Lock()

    def upload_form(
        self,
        key: str,
        *,
        content_type: str,
        size: int,
        sha256_hex: str,
        expires_in: timedelta,
        now: datetime,
    ) -> UploadForm:
        expires_at = now + expires_in
        with self._lock:
            self._forms[key] = (content_type, size, sha256_hex, expires_at)
        return UploadForm(
            url=self.URL,
            fields={
                "key": key,
                "Content-Type": content_type,
                "x-amz-checksum-algorithm": "SHA256",
                "x-amz-checksum-sha256": sha256_base64(sha256_hex),
            },
            expires_at=expires_at,
        )

    def receive(self, key: str, data: bytes, *, content_type: str, now: datetime) -> None:
        """Upload through a form, refused exactly where S3 would refuse it."""
        with self._lock:
            form = self._forms.get(key)
            if form is None:
                raise PermissionError("no upload form for this key")
            wanted_type, wanted_size, wanted_sha, expires_at = form
            if now >= expires_at:
                raise PermissionError("the upload form has expired")
            if content_type != wanted_type or len(data) != wanted_size:
                raise PermissionError("the file does not match the form")
            if hashlib.sha256(data).hexdigest() != wanted_sha:
                raise PermissionError("the file's fingerprint does not match the form")
            self._objects[key] = (data, content_type)

    def describe(self, key: str) -> StoredObject | None:
        with self._lock:
            stored = self._objects.get(key)
        if stored is None:
            return None
        return StoredObject(size=len(stored[0]), content_type=stored[1])

    def read(self, key: str, *, max_bytes: int) -> bytes:
        with self._lock:
            stored = self._objects.get(key)
        if stored is None:
            raise KeyError(key)
        if len(stored[0]) > max_bytes:
            raise ObjectTooLarge(key)
        return stored[0]

    def write(self, key: str, data: bytes, *, content_type: str) -> None:
        with self._lock:
            self._objects[key] = (data, content_type)

    def delete(self, key: str) -> None:
        with self._lock:
            self._objects.pop(key, None)

    def view_url(self, key: str, *, expires_in: timedelta, filename: str) -> str:
        return f"{self.URL}/{key}?filename={filename}&expires={int(expires_in.total_seconds())}"

    def destroy(self, key: str) -> None:
        # No versions are kept here, so deleting is destroying.
        self.delete(key)

    def keys(self) -> set[str]:
        """What is stored, for tests."""
        with self._lock:
            return set(self._objects)

    def clear(self) -> None:
        with self._lock:
            self._objects.clear()
            self._forms.clear()


_memory_store = MemoryFileStore()
_s3_store: S3FileStore | None = None
_s3_lock = threading.Lock()


def get_file_store() -> FileStore:
    """FastAPI dependency: the store this deployment is configured for.

    S3 whenever a bucket is set. Without one, the in-memory stand-in in local
    and test only; anywhere else this refuses loudly rather than pretend to
    keep somebody's proof.
    """
    global _s3_store
    if settings.uploads_bucket:
        with _s3_lock:
            if _s3_store is None or _s3_store.bucket != settings.uploads_bucket:
                _s3_store = S3FileStore(settings.uploads_bucket, s3_client())
            return _s3_store
    if settings.environment in MEMORY_STORE_ENVIRONMENTS:
        return _memory_store
    raise StorageNotConfigured(
        f"no uploads bucket configured for environment '{settings.environment}'"
    )


def memory_store() -> MemoryFileStore:
    """The stand-in itself, for tests that upload through it."""
    return _memory_store
