"""Downloading your own data: what it contains, and what it must never contain."""

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import app.db.models  # noqa: F401  — registers every table on Base.metadata
from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ForbiddenExportField,
    allow,
    build_section,
    to_json_value,
)
from app.core.rate_limit import limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth import export_service
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.account import Account
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns import service as campaigns_service
from app.modules.campaigns.models import Application
from app.modules.deal_memo import service as deal_memo_service
from app.modules.notifications import service as notifications_service
from app.modules.payment_status import service as payment_service
from tests.factories import (
    FIXED_NOW,
    build_auth_session,
    build_brand,
    build_campaign,
    build_creator,
    create_account,
)

URL = "/api/v1/me/export"

# Which declared field list belongs to which table. The structural tests read
# this, so a field list added without a table here is noticed.
FIELD_LISTS: dict[str, tuple[str, ...]] = {
    "account": export_service.ACCOUNT_EXPORT_FIELDS,
    "brand": export_service.BRAND_EXPORT_FIELDS,
    "creator": export_service.CREATOR_EXPORT_FIELDS,
    "auth_session": export_service.SESSION_EXPORT_FIELDS,
    "campaign": campaigns_service.CAMPAIGN_EXPORT_FIELDS,
    "application": campaigns_service.APPLICATION_EXPORT_FIELDS,
    "deal_memo": deal_memo_service.MEMO_EXPORT_FIELDS,
    "deliverable_proof": deal_memo_service.PROOF_EXPORT_FIELDS,
    "notification": notifications_service.EXPORT_FIELDS,
    "payment_status": payment_service.EXPORT_FIELDS,
}


@pytest.fixture
def now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def client(db, now) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def auth_for(account: Account, now: datetime) -> dict[str, str]:
    token, _ = create_access_token(account.id, account.role, now)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scenario(db, now) -> dict:
    """A brand and a creator who have actually dealt with each other."""
    brand = build_brand(db, name="Amma Sweets", email="hello@ammasweets.in")
    db.add(brand)
    db.flush()

    campaign = build_campaign(db, brand_id=brand.id, title="Pongal sweets launch")
    db.add(campaign)
    db.flush()

    creator = build_creator(db, handle="priya.eats")
    db.add(creator)
    db.flush()

    application = Application(
        campaign_id=campaign.id,
        creator_id=creator.id,
        pitch="I cover street food across Madurai and would love to film this.",
        quoted_amount_paise=900_000,
    )
    db.add(application)
    db.flush()

    notifications_service.record(
        db,
        account_id=brand.account_id,
        notification_type="application_received",
        now=now,
        campaign_id=campaign.id,
        application_id=application.id,
        details={"campaign_title": campaign.title, "creator_handle": creator.handle},
    )
    db.add(build_auth_session(db, account_id=brand.account_id))
    db.flush()

    return {
        "brand": brand,
        "creator": creator,
        "campaign": campaign,
        "application": application,
        "brand_account": db.get(Account, brand.account_id),
        "creator_account": db.get(Account, creator.account_id),
    }


# --- the completeness guard ----------------------------------------------


def test_every_table_is_either_exported_or_explained():
    """The point of the whole design.

    When a new table lands — `payment_status` is next — this fails until
    somebody decides whether it belongs in a person's export. Forgetting is
    not an available outcome.
    """
    accounted_for = export_service.exported_tables() | set(export_service.NOT_EXPORTED)

    assert set(Base.metadata.tables) == accounted_for


def test_nothing_claims_a_table_that_does_not_exist():
    """Catches a rename that left a stale entry behind."""
    accounted_for = export_service.exported_tables() | set(export_service.NOT_EXPORTED)

    assert accounted_for <= set(Base.metadata.tables)


def test_everything_left_out_says_why():
    for table, reason in export_service.NOT_EXPORTED.items():
        assert len(reason) > 40, f"{table} needs a real explanation"


@pytest.mark.parametrize(("table", "fields"), sorted(FIELD_LISTS.items()))
def test_every_declared_field_is_a_real_column(table, fields):
    """A typo in a field list would otherwise only surface once real data
    existed, as an AttributeError on a live export."""
    columns = {column.name for column in Base.metadata.tables[table].columns}

    assert set(fields) <= columns, f"{table}: {set(fields) - columns}"


@pytest.mark.parametrize(("table", "fields"), sorted(FIELD_LISTS.items()))
def test_no_field_list_contains_a_secret(table, fields):
    allow(*fields)  # raises if any name looks like a secret


def test_declaring_a_secret_field_is_refused():
    with pytest.raises(ForbiddenExportField):
        allow("id", "token_hash")

    with pytest.raises(ForbiddenExportField):
        allow("code_hash")


# --- who may ask ----------------------------------------------------------


def test_an_export_needs_a_login(client):
    response = client.get(URL)

    assert response.status_code == 401


def test_there_is_no_way_to_ask_for_someone_else(client, scenario, now):
    """The account comes from the token, so there is no identifier to change.

    A query parameter naming another account is simply ignored.
    """
    headers = auth_for(scenario["brand_account"], now)
    other = scenario["creator_account"]

    response = client.get(f"{URL}?account_id={other.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["account_id"] == str(scenario["brand_account"].id)


# --- what a brand gets ----------------------------------------------------


def test_a_brand_gets_its_own_records(client, scenario, now):
    body = client.get(URL, headers=auth_for(scenario["brand_account"], now)).json()
    data = body["data"]

    assert data["account"][0]["phone"] == scenario["brand_account"].phone
    assert data["brand_profile"][0]["name"] == "Amma Sweets"
    assert data["campaigns"][0]["title"] == "Pongal sweets launch"
    assert data["applications_received"][0]["pitch"].startswith("I cover street food")
    assert data["notifications"][0]["notification_type"] == "application_received"
    assert len(data["login_sessions"]) == 1


def test_a_brand_sees_the_other_side_only_by_public_handle(client, scenario, now):
    body = client.get(URL, headers=auth_for(scenario["brand_account"], now)).json()

    received = body["data"]["applications_received"][0]
    assert received["creator_handle"] == "priya.eats"
    assert received["campaign_title"] == "Pongal sweets launch"


def test_a_brands_export_never_carries_the_creators_phone(client, scenario, now):
    """The single most important assertion in this file."""
    creator_phone = scenario["creator_account"].phone

    text = client.get(URL, headers=auth_for(scenario["brand_account"], now)).text

    assert creator_phone not in text


# --- what a creator gets --------------------------------------------------


def test_a_creator_gets_its_own_records(client, scenario, now):
    body = client.get(URL, headers=auth_for(scenario["creator_account"], now)).json()
    data = body["data"]

    assert data["creator_profile"][0]["handle"] == "priya.eats"
    assert data["applications_sent"][0]["campaign_title"] == "Pongal sweets launch"
    assert "campaigns" not in data
    assert "applications_received" not in data


def test_a_creators_export_never_carries_the_brands_contact_details(
    client, scenario, now
):
    text = client.get(URL, headers=auth_for(scenario["creator_account"], now)).text

    assert "hello@ammasweets.in" not in text
    assert scenario["brand_account"].phone not in text


def test_a_session_token_is_never_in_an_export(client, scenario, now):
    from app.modules.auth.models.auth_session import AuthSession

    body = client.get(URL, headers=auth_for(scenario["brand_account"], now)).json()
    exported = body["data"]["login_sessions"][0]

    assert "token_hash" not in exported
    assert set(exported) == set(export_service.SESSION_EXPORT_FIELDS)
    assert AuthSession.token_hash is not None  # the column exists; we withhold it


# --- an account with nothing yet ------------------------------------------


def test_a_brand_new_account_still_gets_a_file(client, db, now):
    """Someone who signed up and stopped still has an account and a right to it."""
    account = create_account(db, "creator")

    body = client.get(URL, headers=auth_for(account, now)).json()

    assert body["data"]["account"][0]["id"] == str(account.id)
    assert body["data"]["login_sessions"] == []
    assert "creator_profile" not in body["data"]


# --- the file explains itself ---------------------------------------------


def test_the_manifest_describes_every_section(client, scenario, now):
    body = client.get(URL, headers=auth_for(scenario["brand_account"], now)).json()

    named = {entry["section"] for entry in body["manifest"]}
    assert named == set(body["data"])
    for entry in body["manifest"]:
        assert entry["purpose"].strip(), f"{entry['section']} has no stated purpose"
        assert entry["records"] == len(body["data"][entry["section"]])


def test_the_file_says_what_was_left_out(client, scenario, now):
    body = client.get(URL, headers=auth_for(scenario["brand_account"], now)).json()

    left_out = {entry["data"]: entry["reason"] for entry in body["not_included"]}
    assert "otp_challenge" in left_out
    assert "hash" in left_out["otp_challenge"]


def test_the_file_carries_its_version_and_a_timestamp(client, scenario, now):
    body = client.get(URL, headers=auth_for(scenario["brand_account"], now)).json()

    assert body["schema_version"] == export_service.SCHEMA_VERSION
    assert body["generated_at"] == "2026-09-17T12:00:00Z"


def test_the_file_does_not_claim_we_hold_money(client, scenario, now):
    """CLAUDE.md section 2: we record payment, we never hold it.

    NOTE FOR THE BANNED-TERM CHECK (testing.md section 7, gate 7): the four
    forbidden words appear on the next line because this is the test that
    forbids them. This is the one place they are allowed to exist, and the
    checker must exclude it. Everywhere else, a hit is a real fault.
    """
    text = client.get(URL, headers=auth_for(scenario["brand_account"], now)).text.lower()

    for word in ("escrow", "wallet", "guaranteed funds", "split settlement"):
        assert word not in text


# --- how it is delivered --------------------------------------------------


def test_it_arrives_as_a_download(client, scenario, now):
    response = client.get(URL, headers=auth_for(scenario["brand_account"], now))

    disposition = response.headers["content-disposition"]
    assert disposition == 'attachment; filename="nicheconnect-export-2026-09-17.json"'


def test_a_copy_is_never_left_in_a_cache(client, scenario, now):
    """Unlike the public Passport, this must not be stored by anything."""
    response = client.get(URL, headers=auth_for(scenario["brand_account"], now))

    assert response.headers["cache-control"] == "no-store"


def test_exports_are_tightly_rate_limited(client, scenario, now):
    """Three an hour: it reads every table an account touches."""
    headers = auth_for(scenario["brand_account"], now)
    for _ in range(3):
        assert client.get(URL, headers=headers).status_code == 200

    response = client.get(URL, headers=headers)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


# --- turning values into JSON ---------------------------------------------


def test_timestamps_come_out_as_utc_with_a_z():
    assert to_json_value(FIXED_NOW) == "2026-09-17T12:00:00Z"


def test_a_naive_timestamp_is_read_as_utc_not_local_time():
    """Reading it as local time would shift every date in the file."""
    naive = datetime(2026, 9, 17, 12, 0)

    assert to_json_value(naive) == "2026-09-17T12:00:00Z"


def test_a_type_with_no_agreed_form_is_an_error():
    """Better a failed export than a column silently stringified."""
    with pytest.raises(TypeError):
        to_json_value(object())


def test_a_section_admits_when_it_had_more_rows(monkeypatch):
    monkeypatch.setattr("app.core.export.MAX_ROWS_PER_SECTION", 2)

    class Row:
        def __init__(self, value):
            self.id = value

    section = build_section(
        "things",
        table="account",
        purpose="testing",
        objects=[Row(1), Row(2), Row(3)],
        fields=("id",),
    )

    assert section.truncated is True
    assert len(section.records) == 2
    assert section.manifest_entry()["truncated"] is True


def test_a_section_within_the_cap_says_nothing_about_truncation():
    section = build_section(
        "things", table="account", purpose="testing", objects=[], fields=("id",)
    )

    assert section.truncated is False
    assert "truncated" not in section.manifest_entry()
    assert MAX_ROWS_PER_SECTION > 0
