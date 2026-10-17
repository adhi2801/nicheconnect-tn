"""The second check before a risky change, as a test needs it (item 82, D-107).

Each helper asks for a code through the API, exactly as an app would, and
reads it from a fake sender put in place for that one request, so a test of
something else (what an export holds, what a brand sees) still goes through
the real check rather than around it.
"""

from collections.abc import Mapping
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from app.main import app
from app.modules.auth.sender import FakeOtpSender, get_otp_sender

STEP_UP_URL = "/api/v1/me/step-up"
EXPORT_URL = "/api/v1/me/export"
LOGOUT_ALL_URL = "/api/v1/auth/logout-all"


def ask_for_code(
    client: TestClient,
    headers: Mapping[str, str],
    action: str,
    *,
    upi_id: str | None = None,
) -> str:
    """A fresh code for `action` (and `upi_id`), as sent to the person's phone."""
    body: dict[str, Any] = {"action": action}
    if upi_id is not None:
        body["upi_id"] = upi_id
    sender = FakeOtpSender()
    earlier = app.dependency_overrides.get(get_otp_sender)
    app.dependency_overrides[get_otp_sender] = lambda: sender
    try:
        response = client.post(STEP_UP_URL, json=body, headers=dict(headers))
    finally:
        if earlier is None:
            app.dependency_overrides.pop(get_otp_sender, None)
        else:
            app.dependency_overrides[get_otp_sender] = earlier
    assert response.status_code == 202, response.text
    [sent] = sender.sent
    return sent.code


def with_code(
    client: TestClient,
    headers: Mapping[str, str],
    action: str,
    *,
    upi_id: str | None = None,
) -> dict[str, str]:
    """`headers`, plus a fresh code for exactly this change."""
    code = ask_for_code(client, headers, action, upi_id=upi_id)
    return {**headers, "Step-Up-Code": code}


def download_export(client: TestClient, headers: Mapping[str, str]) -> Response:
    """The person's data export, through the second check."""
    return client.get(EXPORT_URL, headers=with_code(client, headers, "download_export"))


def log_out_everywhere(client: TestClient, headers: Mapping[str, str]) -> Response:
    """Log out of every device, through the second check."""
    return client.post(
        LOGOUT_ALL_URL, headers=with_code(client, headers, "log_out_everywhere")
    )
