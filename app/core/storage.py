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
"""

import base64
import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from app.core.config import settings

# Outside AWS nothing is uploaded for real, so the stand-in is only allowed
# where nobody's files are at stake.
MEMORY_STORE_ENVIRONMENTS = frozenset({"local", "test"})


class StorageNotConfigured(RuntimeError):
    """No bucket is set in an environment that must have one."""


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

    def view_url(self, key: str, *, expires_in: timedelta, filename: str) -> str: ...


def sha256_base64(sha256_hex: str) -> str:
    """S3 wants the fingerprint as base64 of the raw digest, not as hex."""
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")


# --- S3 -----------------------------------------------------------------------


class S3FileStore:
    """The real store: one private bucket, reached with the task's own role."""

    def __init__(self, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self._client = client

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
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return None
            raise
        return StoredObject(
            size=int(head["ContentLength"]), content_type=head.get("ContentType")
        )

    def read(self, key: str, *, max_bytes: int) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        if int(response["ContentLength"]) > max_bytes:
            response["Body"].close()
            raise ObjectTooLarge(key)
        data: bytes = response["Body"].read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ObjectTooLarge(key)
        return data

    def write(self, key: str, data: bytes, *, content_type: str) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode(
                "ascii"
            ),
        )

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

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
            connect_timeout=3,
            read_timeout=10,
            retries={"mode": "standard", "max_attempts": 3},
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
