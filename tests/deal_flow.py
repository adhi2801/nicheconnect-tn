"""The deal journey as test helpers: campaign, application, memo, accepted.

Proof, payment and dispute tests all start from an accepted memo, so the way
to get one lives here rather than inside any one test module. The `clock`
and `client` fixtures these helpers expect come from tests/modules/conftest.py.
"""

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.auth.tokens import create_access_token
from tests.factories import build_brand, build_creator

CAMPAIGNS_URL = "/api/v1/campaigns"
MEMOS_URL = "/api/v1/deal-memos"
NOTIFICATIONS_URL = "/api/v1/notifications"
PITCH = "I run a Madurai street-food page with 12,000 local followers."
LINK = "https://www.instagram.com/reel/abc123/"


class Clock:
    """The time the app sees. Tests move it instead of sleeping."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class User:
    """A signed-in account whose token is minted at the clock's current time."""

    def __init__(self, account_id: uuid.UUID, role: str, clock: Clock) -> None:
        self.account_id = account_id
        self.role = role
        self.clock = clock

    @property
    def headers(self) -> dict[str, str]:
        token, _ = create_access_token(self.account_id, self.role, self.clock.now)
        return {"Authorization": f"Bearer {token}"}


def brand_user(db: Session, clock: Clock) -> User:
    brand = build_brand(db, email=f"brand-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return User(brand.account_id, "brand", clock)


def creator_user(db: Session, clock: Clock) -> User:
    creator = build_creator(db, handle=f"proof{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


def accepted_memo(client: TestClient, brand: User, creator: User, **memo_fields: object) -> str:
    """A whole journey: campaign, application, acceptance, memo, accepted."""
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Pongal sweets launch",
            "description": "Three reels featuring our new sweet box.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "3 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    body: dict[str, object] = {
        "deliverables": "3 Instagram reels, 1 story set.",
        "fee_amount_paise": 800_000,
    }
    body.update(memo_fields)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}", json=body, headers=brand.headers
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    accepted = client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)
    assert accepted.status_code == 200, accepted.text
    return str(memo_id)
