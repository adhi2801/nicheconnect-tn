"""What is switched on for each account, over HTTP (item 92, D-160).

Each account is told its own answer while a feature reaches only a share,
a team member as their brand; and the brief route refuses a brand outside the
share with the code it uses when drafting is off. The rule is test_rollout.py's.
"""

import pytest

from app.core import features, rollout
from app.core.config import settings
from tests.deal_flow import brand_user, creator_user


@pytest.fixture
def share(monkeypatch):
    def set_to(percent: int, feature: str = "brief_drafting") -> None:
        monkeypatch.setattr(settings, "feature_rollout", {feature: percent})

    return set_to


def test_an_account_is_told_its_own_answer(client, db, clock, share, monkeypatch):
    monkeypatch.setattr(settings, "brief_drafting_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", type(settings.secret_key)("k"))
    brand = brand_user(db, clock)
    bucket = rollout.bucket("brief_drafting", brand.account_id)

    share(bucket + 1)
    inside = client.get("/api/v1/me/features", headers=brand.headers)
    share(bucket)
    outside = client.get("/api/v1/me/features", headers=brand.headers)

    assert inside.status_code == 200, inside.text
    assert inside.headers["Cache-Control"] == "private, max-age=300"
    assert inside.json()["brief_drafting"]["on"] is True
    assert outside.json()["brief_drafting"]["on"] is False


def test_a_team_member_is_told_their_brand_s_answer(
    client, db, clock, share, monkeypatch
):
    from tests.modules.me.test_team_api import join

    monkeypatch.setattr(settings, "brief_drafting_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", type(settings.secret_key)("k"))
    owner = brand_user(db, clock)
    member = join(client, db, clock, owner, "campaigns")
    share(rollout.bucket("brief_drafting", owner.account_id) + 1)

    found = client.get("/api/v1/me/features", headers=member.headers).json()

    assert found["brief_drafting"]["on"] is True


def test_a_creator_is_answered_too(client, db, clock):
    response = client.get("/api/v1/me/features", headers=creator_user(db, clock).headers)

    assert response.status_code == 200, response.text
    assert set(response.json()) == set(features.FeaturesRead.model_fields)


def test_my_features_needs_a_login(client):
    assert client.get("/api/v1/me/features").status_code == 401


def test_my_features_is_rate_limited(client, db, clock):
    from app.modules.me.features_router import READ_LIMIT

    user = creator_user(db, clock)
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get("/api/v1/me/features", headers=user.headers).status_code == 200
    assert client.get("/api/v1/me/features", headers=user.headers).status_code == 429


def test_a_brand_outside_the_share_is_refused_as_if_drafting_were_off(
    client, db, clock, share
):
    from app.modules.campaigns.brief_drafter import Drafted, set_drafter
    from tests.modules.campaigns.test_brief_drafts_api import FIELDS

    class Fake:
        def draft(self, idea: str) -> Drafted:
            return Drafted(FIELDS, None, "fake")

    set_drafter(Fake())
    try:
        brand = brand_user(db, clock)
        bucket = rollout.bucket("brief_drafting", brand.account_id)
        body = {"idea": "Two reels for our Pongal millet laddu box, Madurai."}

        share(bucket)
        refused = client.post("/api/v1/brief-drafts", json=body, headers=brand.headers)
        share(bucket + 1)
        asked = client.post("/api/v1/brief-drafts", json=body, headers=brand.headers)
    finally:
        set_drafter(None)

    assert refused.status_code == 503
    assert refused.json()["code"] == "brief_drafting_unavailable"
    assert asked.status_code == 202, asked.text
