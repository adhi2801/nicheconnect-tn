"""What is switched on (R6 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

The rules worth proving: each feature reads the very setting its own routes
are switched by, so the two can never disagree; each off code is the one its
routes really answer; it needs no login and is cached briefly.
"""

import pytest
from fastapi.testclient import TestClient

from app.core import features
from app.core.config import settings
from app.main import app
from app.modules.auth.exceptions import PasskeysNotOpen
from app.modules.payment_status.exceptions import UpiNotOpenYet
from app.modules.profiles.exceptions import ConnectionsOff

URL = "/api/v1/features"


@pytest.fixture
def client() -> TestClient:
    from app.core.rate_limit import limiter

    limiter.reset()
    return TestClient(app)


def test_it_needs_no_login_and_is_cached_for_five_minutes(client):
    response = client.get(URL)

    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert set(response.json()) == {
        "passkeys",
        "connected_accounts",
        "upi_ids",
        "passport_indexing",
        "results_from_proof",
    }


def test_each_off_code_is_the_one_its_routes_answer():
    found = features.current()

    assert found.passkeys.off_code == PasskeysNotOpen.code
    assert found.connected_accounts.off_code == ConnectionsOff.code
    assert found.upi_ids.off_code == UpiNotOpenYet.code


@pytest.mark.parametrize(
    ("setting", "on_value", "feature"),
    [
        ("passkey_rp_id", "colyv.example", "passkeys"),
        ("platform_connections_enabled", True, "connected_accounts"),
        ("upi_notice_version", "v1", "upi_ids"),
        ("passport_indexing", True, "passport_indexing"),
    ],
)
def test_each_feature_follows_the_setting_its_routes_follow(
    monkeypatch, client, setting, on_value, feature
):
    monkeypatch.setattr(settings, setting, None if on_value is not True else False)
    assert client.get(URL).json()[feature]["on"] is False

    monkeypatch.setattr(settings, setting, on_value)
    assert client.get(URL).json()[feature]["on"] is True


def test_results_from_proof_need_the_key_as_well_as_the_switch(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "proof_reading_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert features.current().results_from_proof.on is False

    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("x" * 40))
    assert features.current().results_from_proof.on is True
