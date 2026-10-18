"""A passkey as a test needs one: a software authenticator (item 79, D-113).

It makes real WebAuthn answers, with a real P-256 key and real signatures,
in exactly the JSON a browser or phone sends, so every check fido2 and our
own code make runs for real; only the phone's fingerprint prompt is skipped.
Each part a test may want to get wrong (the origin, the domain, the
counter, the verified-user flag) can be set per answer.
"""

import hashlib
import secrets
from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fido2.cose import ES256
from fido2.utils import websafe_decode, websafe_encode
from fido2.webauthn import (
    AttestationObject,
    AttestedCredentialData,
    AuthenticatorData,
    CollectedClientData,
)

from app.core.config import settings

RP_ID = "nicheconnect.test"
ORIGIN = "https://app.nicheconnect.test"
FLAG = AuthenticatorData.FLAG


@pytest.fixture
def passkeys_on(monkeypatch) -> Iterator[None]:
    """Passkeys switched on, for a domain only tests use."""
    monkeypatch.setattr(settings, "passkey_rp_id", RP_ID)
    monkeypatch.setattr(settings, "passkey_origins", ORIGIN)
    yield


class SoftAuthenticator:
    """One passkey on one pretend phone."""

    def __init__(self, *, synced: bool = True, counter_step: int = 0) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)
        self.synced = synced
        # Synced passkeys keep their counter at 0; a security key counts up.
        self.counter = 0
        self.counter_step = counter_step
        self.user_handle: bytes | None = None

    def create(
        self,
        options: Mapping[str, Any],
        *,
        origin: str = ORIGIN,
        rp_id: str = RP_ID,
        verified: bool = True,
    ) -> dict[str, Any]:
        """The answer to a sign-up challenge: a new key for this account."""
        public = options["publicKey"]
        self.user_handle = websafe_decode(public["user"]["id"])
        client_data = CollectedClientData.create(
            type="webauthn.create",
            challenge=websafe_decode(public["challenge"]),
            origin=origin,
        )
        attested = AttestedCredentialData.create(
            bytes(16),
            self.credential_id,
            ES256.from_cryptography_key(self.private_key.public_key()),
        )
        auth_data = AuthenticatorData.create(
            hashlib.sha256(rp_id.encode()).digest(),
            self._flags(verified) | FLAG.AT,
            self.counter,
            bytes(attested),
        )
        attestation = AttestationObject.create("none", auth_data, {})
        return {
            "id": websafe_encode(self.credential_id),
            "rawId": websafe_encode(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": websafe_encode(client_data),
                "attestationObject": websafe_encode(bytes(attestation)),
            },
            "clientExtensionResults": {},
        }

    def get(
        self,
        options: Mapping[str, Any],
        *,
        origin: str = ORIGIN,
        rp_id: str = RP_ID,
        verified: bool = True,
        counter: int | None = None,
    ) -> dict[str, Any]:
        """The answer to a login or change challenge, signed by this key."""
        public = options["publicKey"]
        client_data = CollectedClientData.create(
            type="webauthn.get",
            challenge=websafe_decode(public["challenge"]),
            origin=origin,
        )
        self.counter += self.counter_step
        auth_data = AuthenticatorData.create(
            hashlib.sha256(rp_id.encode()).digest(),
            self._flags(verified),
            self.counter if counter is None else counter,
        )
        signature = self.private_key.sign(
            bytes(auth_data) + client_data.hash, ec.ECDSA(hashes.SHA256())
        )
        response: dict[str, Any] = {
            "clientDataJSON": websafe_encode(client_data),
            "authenticatorData": websafe_encode(bytes(auth_data)),
            "signature": websafe_encode(signature),
        }
        if self.user_handle is not None:
            response["userHandle"] = websafe_encode(self.user_handle)
        return {
            "id": websafe_encode(self.credential_id),
            "rawId": websafe_encode(self.credential_id),
            "type": "public-key",
            "response": response,
            "clientExtensionResults": {},
        }

    def _flags(self, verified: bool) -> AuthenticatorData.FLAG:
        flags = FLAG.UP
        if verified:
            flags |= FLAG.UV
        if self.synced:
            flags |= FLAG.BE | FLAG.BS
        return flags
