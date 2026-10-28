"""Look-alike brand names, through the API (item 75, D-118, option B).

A creator sees the warning beside the brand's name on its campaigns and its
payment record; a brand under such a name cannot publish until it verifies
the domain of the brand it resembles.
"""

import uuid
from datetime import timedelta

import pytest

from app.modules.auth.models.brand import Brand
from app.modules.profiles.brand_domain_models import BrandDomain
from app.modules.profiles.brand_domains import TOKEN_LIFETIME, new_token
from tests.deal_flow import CAMPAIGNS_URL, User, creator_user
from tests.factories import build_brand, create_account
from tests.query_counts import queries_for

CYRILLIC_U = chr(0x0443)
DRAFT = {
    "title": "Diwali hampers",
    "description": "Two reels on our festive hamper.",
    "campaign_type": "paid",
    "budget_min_paise": 500_000,
    "budget_max_paise": 1_000_000,
    "cities": ["Madurai"],
    "niches": ["food"],
    "deliverables": "2 Instagram reels",
}


def brand_named(db, clock, name: str) -> tuple[User, Brand]:
    brand = build_brand(db, name=name, email=f"b-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return User(brand.account_id, "brand", clock), brand


def verify_domain(db, clock, brand: Brand, domain: str) -> None:
    """A domain the brand has proved it controls (item 74), as the daily check leaves it."""
    db.add(
        BrandDomain(
            brand_id=brand.id,
            domain=domain,
            token=new_token(),
            status="verified",
            claimed_at=clock.now,
            token_expires_at=clock.now + TOKEN_LIFETIME,
            verified_at=clock.now,
            last_checked_at=clock.now,
            last_result="found",
        )
    )
    db.flush()


def draft(client, user: User) -> str:
    response = client.post(CAMPAIGNS_URL, json=DRAFT, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def publish(client, user: User, campaign_id: str):
    return client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=user.headers)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.mark.parametrize(
    "name",
    ["Nykaa Collabs", "N" + CYRILLIC_U + "kaa", "Mamaearth Official India", "Zomatto"],
)
def test_a_borrowed_name_cannot_publish(client, db, clock, name):
    brand, _ = brand_named(db, clock, name)

    response = publish(client, brand, draft(client, brand))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "brand_name_needs_domain"
    assert "POST /api/v1/brands/me/domain" in body["detail"]


def test_the_refusal_names_the_brand_and_its_domain(client, db, clock):
    brand, _ = brand_named(db, clock, "Nykaa Collabs")

    detail = publish(client, brand, draft(client, brand)).json()["detail"]

    assert "Nykaa" in detail and "nykaa.com" in detail


def test_verifying_the_real_domain_lets_the_real_brand_publish(client, db, clock):
    user, brand = brand_named(db, clock, "Nykaa")
    campaign_id = draft(client, user)
    assert publish(client, user, campaign_id).status_code == 409

    verify_domain(db, clock, brand, "nykaa.com")

    published = publish(client, user, campaign_id)
    assert published.status_code == 200, published.text
    assert published.json()["brand_name_flag"] is None


def test_a_look_alike_domain_does_not(client, db, clock):
    user, brand = brand_named(db, clock, "Nykaa Collabs")
    verify_domain(db, clock, brand, "nykaa-collabs.in")

    assert publish(client, user, draft(client, user)).status_code == 409


def test_an_ordinary_name_publishes_and_carries_no_flag(client, db, clock):
    user, _ = brand_named(db, clock, "Amma Sweets")

    response = publish(client, user, draft(client, user))

    assert response.status_code == 200, response.text
    assert response.json()["brand_name_flag"] is None


def test_a_creator_sees_the_warning_on_a_campaign_already_open(
    client, db, clock, creator
):
    """Published before the name was flagged: it stays open, and says so."""
    user, brand = brand_named(db, clock, "Amma Sweets")
    campaign_id = draft(client, user)
    assert publish(client, user, campaign_id).status_code == 200
    brand.name = "Nykaa Official"
    db.flush()

    shown = client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=creator.headers)

    assert shown.status_code == 200, shown.text
    assert shown.json()["brand_name_flag"] == {
        "resembles_name": "Nykaa",
        "resembles_domain": "nykaa.com",
        "mixed_script": False,
    }


def test_a_brand_verified_here_protects_its_name(client, db, clock):
    real_user, real = brand_named(db, clock, "Chennai Bakes")
    verify_domain(db, clock, real, "chennaibakes.in")
    copy_user, _ = brand_named(db, clock, "Chennai Bakes Official")

    assert publish(client, real_user, draft(client, real_user)).status_code == 200
    refused = publish(client, copy_user, draft(client, copy_user))
    assert refused.status_code == 409
    assert "chennaibakes.in" in refused.json()["detail"]


def test_a_mixed_alphabet_name_is_held_and_says_why(client, db, clock):
    user, _ = brand_named(db, clock, "Amm" + chr(0x0430) + " Sweets")

    refused = publish(client, user, draft(client, user))

    assert refused.status_code == 409
    assert "alphabet" in refused.json()["detail"]


def test_the_payment_record_carries_the_warning(client, db, clock, creator):
    _, brand = brand_named(db, clock, "Mamaearth India")

    record = client.get(f"/api/v1/brands/{brand.id}/reliability", headers=creator.headers)

    assert record.status_code == 200, record.text
    assert record.json()["brand_name_flag"]["resembles_name"] == "Mamaearth"


def test_flags_on_a_page_cost_the_same_queries_however_many_brands(
    client, db, clock, creator
):
    def open_campaign(name: str) -> None:
        user, brand = brand_named(db, clock, name)
        verify_domain(db, clock, brand, f"{uuid.uuid4().hex[:10]}.in")
        assert publish(client, user, draft(client, user)).status_code == 200

    open_campaign("Amma Sweets")
    url = f"{CAMPAIGNS_URL}/discover"
    few = queries_for(client, url, creator.headers)
    # Names far apart: two a letter apart would rightly hold the second.
    for name in (
        "Kovai Snacks",
        "Madurai Silks",
        "Salem Steel",
        "Erode Turmeric",
        "Trichy Tiffin",
        "Nellai Halwa",
    ):
        open_campaign(name)
    clock.advance(timedelta(seconds=1))

    assert queries_for(client, url, creator.headers) == few


LOOK_ALIKES_URL = "/api/v1/admin/brands/look-alikes"


def test_admins_see_every_flagged_brand_and_no_other(client, db, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)
    _, fake = brand_named(db, clock, "Nykaa Collabs " + uuid.uuid4().hex[:6])
    _, plain = brand_named(db, clock, "Amma Sweets")

    response = client.get(LOOK_ALIKES_URL, headers=admin.headers)

    assert response.status_code == 200, response.text
    listed = {item["brand_id"]: item for item in response.json()["items"]}
    assert listed[str(fake.id)]["resembles_domain"] == "nykaa.com"
    assert listed[str(fake.id)]["account_id"] == str(fake.account_id)
    assert str(plain.id) not in listed


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_anyone_but_an_admin_is_told_it_does_not_exist(client, db, clock, role):
    user = User(create_account(db, role).id, role, clock)

    assert client.get(LOOK_ALIKES_URL, headers=user.headers).status_code == 404


# --- an admin clearing a genuine name (D-119) -------------------------------------------


def clearance_url(brand: Brand, withdraw: bool = False) -> str:
    return f"/api/v1/admin/brands/{brand.id}/name-clearance" + (
        "/withdraw" if withdraw else ""
    )


NOTE = {"note": "Spoke to the owner; a Coimbatore shop since 2011, no relation."}


@pytest.fixture
def admin(db, clock) -> User:
    return User(create_account(db, "admin").id, "admin", clock)


def test_a_cleared_name_publishes_and_shows_no_warning(client, db, clock, admin, creator):
    user, brand = brand_named(db, clock, "Amazon Organics Coimbatore")
    campaign_id = draft(client, user)
    assert publish(client, user, campaign_id).status_code == 409

    cleared = client.post(clearance_url(brand), json=NOTE, headers=admin.headers)

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["name_cleared"] is True
    published = publish(client, user, campaign_id)
    assert published.status_code == 200, published.text
    assert published.json()["brand_name_flag"] is None
    record = client.get(f"/api/v1/brands/{brand.id}/reliability", headers=creator.headers)
    assert record.json()["brand_name_flag"] is None
    listed = client.get(LOOK_ALIKES_URL, headers=admin.headers).json()["items"]
    assert str(brand.id) not in {item["brand_id"] for item in listed}


def test_clearing_and_withdrawing_go_in_the_admin_log(client, db, clock, admin):
    _, brand = brand_named(db, clock, "Nykaa Collabs")
    client.post(clearance_url(brand), json=NOTE, headers=admin.headers)
    client.post(clearance_url(brand, withdraw=True), json=NOTE, headers=admin.headers)

    log = client.get("/api/v1/admin/actions", headers=admin.headers).json()["items"]
    mine = [
        entry["action"]
        for entry in log
        if entry["subject_account_id"] == str(brand.account_id)
    ]
    assert mine == ["withdraw_brand_name_clearance", "clear_brand_name"]
    assert all(
        entry["note"] == NOTE["note"]
        for entry in log
        if entry["subject_account_id"] == str(brand.account_id)
    )


def test_a_rename_is_held_again_until_looked_at(client, db, clock, admin):
    user, brand = brand_named(db, clock, "Nykaa Collabs")
    client.post(clearance_url(brand), json=NOTE, headers=admin.headers)
    brand.name = "Nykaa Collabs India"
    db.flush()

    assert publish(client, user, draft(client, user)).status_code == 409


def test_a_withdrawn_clearance_holds_the_name_again(client, db, clock, admin):
    user, brand = brand_named(db, clock, "Nykaa Collabs")
    client.post(clearance_url(brand), json=NOTE, headers=admin.headers)

    withdrawn = client.post(
        clearance_url(brand, withdraw=True), json=NOTE, headers=admin.headers
    )

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["name_cleared"] is False
    assert publish(client, user, draft(client, user)).status_code == 409


@pytest.mark.parametrize(
    ("setup", "url_kind", "code"),
    [
        ("plain", "clear", "brand_name_not_flagged"),
        ("cleared", "clear", "brand_name_already_cleared"),
        ("flagged", "withdraw", "brand_name_not_cleared"),
    ],
)
def test_clearances_refuse_what_makes_no_sense(
    client, db, clock, admin, setup, url_kind, code
):
    _, brand = brand_named(
        db, clock, "Amma Sweets" if setup == "plain" else "Nykaa Collabs"
    )
    if setup == "cleared":
        client.post(clearance_url(brand), json=NOTE, headers=admin.headers)

    response = client.post(
        clearance_url(brand, withdraw=url_kind == "withdraw"),
        json=NOTE,
        headers=admin.headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == code


def test_an_unknown_brand_is_not_found(client, db, clock, admin):
    response = client.post(
        f"/api/v1/admin/brands/{uuid.uuid4()}/name-clearance",
        json=NOTE,
        headers=admin.headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_only_an_admin_clears_a_name(client, db, clock, role):
    _, brand = brand_named(db, clock, "Nykaa Collabs")
    user = User(create_account(db, role).id, role, clock)

    response = client.post(clearance_url(brand), json=NOTE, headers=user.headers)

    assert response.status_code == 404
    db.refresh(brand)
    assert brand.name_cleared is None


@pytest.mark.parametrize("note", ["", "ok", "x" * 1001])
def test_a_clearance_needs_a_real_note(client, db, clock, admin, note):
    _, brand = brand_named(db, clock, "Nykaa Collabs")

    response = client.post(
        clearance_url(brand), json={"note": note}, headers=admin.headers
    )

    assert response.status_code == 422


def test_a_held_brand_sees_its_hold_on_its_own_profile(client, db, clock, admin):
    user, brand = brand_named(db, clock, "Nykaa Collabs")

    held = client.get("/api/v1/brands/me", headers=user.headers).json()["name_hold"]
    client.post(clearance_url(brand), json=NOTE, headers=admin.headers)
    lifted = client.get("/api/v1/brands/me", headers=user.headers).json()["name_hold"]

    assert held == {
        "resembles_name": "Nykaa",
        "resembles_domain": "nykaa.com",
        "mixed_script": False,
    }
    assert lifted is None
