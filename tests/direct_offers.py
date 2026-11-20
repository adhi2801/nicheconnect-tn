"""Direct offers (D-189) as test helpers: switch on, send, open, code, accept.

The feature is off until the validation pack's wording exists, so a test
that exercises it turns it on with `switch_on`, which also puts test wording
where the placeholders are. Nothing here is real notice wording.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.models.account import Account
from app.modules.auth.sender import FakeOtpSender
from app.modules.deal_memo import direct_offer_notices as notices
from tests.deal_flow import User
from tests.factories import fake_phone

OFFERS_URL = "/api/v1/direct-offers"
LINK_URL = "/api/v1/direct-offer-link"
STOP_URL = f"{LINK_URL}/stop"
CODE_URL = "/api/v1/auth/direct-offer-link/code"
ACCEPT_URL = "/api/v1/auth/direct-offer-link/accept"
TEST_WORDING = "Test wording for a test run, not a notice."
DUE_ON = "2026-10-15"
FEE = 900_000


# A template name for a test run; nothing is registered under it.
TEST_TEMPLATE = "test_direct_offer_code"


def switch_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The switch on, test wording in place of the link page's placeholder,
    and a test name for the code message's template."""
    monkeypatch.setattr(settings, "direct_offers_enabled", True)
    monkeypatch.setattr(notices, "LINK_PAGE_NOTICE", TEST_WORDING)
    monkeypatch.setattr(settings, "msg91_direct_offer_template", TEST_TEMPLATE)


def offer_body(phone: str | None = None, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "brand_name": "Amma Sweets",
        "brand_phone": phone or fake_phone(),
        "deliverables": "2 Instagram reels about the Diwali sweet box",
        "deliverable_items": [{"platform": "instagram", "format": "reel", "quantity": 2}],
        "fee_amount_paise": FEE,
        "content_due_on": DUE_ON,
        "usage_rights_days": 90,
        "extra_terms": "Tag the shop in the first line.",
    }
    body.update(overrides)
    return body


def send(client: TestClient, creator: User, phone: str | None = None, **overrides: Any):
    return client.post(
        OFFERS_URL, json=offer_body(phone, **overrides), headers=creator.headers
    )


def sent(
    client: TestClient, creator: User, phone: str | None = None, **overrides: Any
) -> dict[str, Any]:
    response = send(client, creator, phone, **overrides)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def link(token: str) -> dict[str, str]:
    return {"Offer-Token": token}


def code_for(client: TestClient, sender: FakeOtpSender, token: str, phone: str) -> str:
    response = client.post(CODE_URL, headers=link(token))
    assert response.status_code == 202, response.text
    code = sender.last_code_for(phone)
    assert code is not None
    return code


def accept_body(code: str, terms_sha256: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "brand_name": "Amma Sweets",
        "email": f"owner-{uuid.uuid4().hex[:12]}@example.com",
        "date_of_birth": "1990-04-14",
        "code": code,
        "terms_sha256": terms_sha256,
    }
    body.update(overrides)
    return body


def accept(
    client: TestClient,
    sender: FakeOtpSender,
    offer: dict[str, Any],
    phone: str,
    **overrides: Any,
):
    code = code_for(client, sender, offer["link_token"], phone)
    return client.post(
        ACCEPT_URL,
        json=accept_body(code, offer["terms_sha256"], **overrides),
        headers=link(offer["link_token"]),
    )


def phone_of(db: Session, user: User) -> str:
    return db.scalars(
        select(Account.phone)
        .where(Account.id == user.account_id)
        .execution_options(populate_existing=True)
    ).one()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
