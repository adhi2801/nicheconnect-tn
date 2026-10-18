"""The second check before a risky change, as a test needs it (item 82, D-107).

Each helper asks for a code through the API, exactly as an app would, and
reads it from a fake sender put in place for that one request, so a test of
something else (what an export holds, what a brand sees) still goes through
the real check rather than around it.
"""

from collections.abc import Mapping
from contextlib import nullcontext
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from app.core.storage import memory_store
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.me import data_export_service

STEP_UP_URL = "/api/v1/me/step-up"
EXPORT_URL = "/api/v1/me/exports"
LOGOUT_ALL_URL = "/api/v1/auth/logout-all"


def ask_for_code(
    client: TestClient,
    headers: Mapping[str, str],
    action: str,
    **fields: str,
) -> str:
    """A fresh code for `action` (and its value), as sent to the person's phone."""
    body: dict[str, Any] = {"action": action, **fields}
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
    **fields: str,
) -> dict[str, str]:
    """`headers`, plus a fresh code for exactly this change."""
    code = ask_for_code(client, headers, action, **fields)
    return {**headers, "Step-Up-Code": code}


def build_exports() -> data_export_service.ExportRun:
    """One run of the export job, on the test's own session, clock and store."""
    db = app.dependency_overrides[get_db]()
    now = app.dependency_overrides[get_now]()
    return data_export_service.run_exports(lambda: nullcontext(db), memory_store(), now)


def ask_for_export(client: TestClient, headers: Mapping[str, str]) -> str:
    """Ask for a data export (no code needed to ask, D-112); its id."""
    asked = client.post(EXPORT_URL, headers=dict(headers))
    assert asked.status_code == 202, asked.text
    export_id: str = asked.json()["id"]
    return export_id


def download_ready_export(
    client: TestClient, headers: Mapping[str, str], export_id: str
) -> Response:
    """Download one ready export, with a code for exactly that export."""
    return client.post(
        f"{EXPORT_URL}/{export_id}/download",
        headers=with_code(client, headers, "download_export", export_id=export_id),
    )


def download_export(client: TestClient, headers: Mapping[str, str]) -> Response:
    """The person's data export, as an app gets it (D-111, D-112).

    Asked for, built by one run of the job, then downloaded with a code for
    that export.
    """
    export_id = ask_for_export(client, headers)
    build_exports()
    return download_ready_export(client, headers, export_id)


def log_out_everywhere(client: TestClient, headers: Mapping[str, str]) -> Response:
    """Log out of every device, through the second check."""
    return client.post(
        LOGOUT_ALL_URL, headers=with_code(client, headers, "log_out_everywhere")
    )
