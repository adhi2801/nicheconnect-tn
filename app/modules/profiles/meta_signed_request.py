"""Reading Meta's `signed_request` (item 29, D-134). Pure.

Meta's data deletion and deauthorize callbacks post a `signed_request`:
`<signature>.<payload>`, both base64url without padding. The signature is
HMAC-SHA256 of the payload's base64 text under our app secret, and the
payload is JSON naming `algorithm` ("HMAC-SHA256") and `user_id`, the
person's id as Meta gave it to our app. Anything else, or a signature that
does not match, is refused: a forged call must never delete or reach
anyone's connection.
"""

import base64
import binascii
import hashlib
import hmac
import json

ALGORITHM = "HMAC-SHA256"
MAX_LENGTH = 4096


def _decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def user_id_from(signed_request: str, app_secret: str) -> str | None:
    """The `user_id` of a genuine signed request, or None for anything else."""
    if not signed_request or len(signed_request) > MAX_LENGTH:
        return None
    signature_b64, dot, payload_b64 = signed_request.partition(".")
    if not dot or not signature_b64 or not payload_b64:
        return None
    try:
        signature = _decode(signature_b64)
        payload = json.loads(_decode(payload_b64))
    except binascii.Error, ValueError, UnicodeDecodeError:
        return None
    expected = hmac.new(
        app_secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    if not isinstance(payload, dict) or payload.get("algorithm") != ALGORITHM:
        return None
    user_id = payload.get("user_id")
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        user_id = str(user_id)
    if not isinstance(user_id, str) or not user_id.isdigit() or len(user_id) > 64:
        return None
    return user_id


def sign(payload: dict[str, object], app_secret: str) -> str:
    """A signed request as Meta makes one: for tests, and to read the format."""
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    signature = hmac.new(
        app_secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(signature).decode().rstrip("=") + "." + payload_b64
