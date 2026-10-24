"""Every route that names an object refuses a stranger (item 100).

security.md section 2: every read or change of an object checks that the
caller may: its owner, a party to the deal, or anyone where it is public by
design. Broken object level authorization is the top API risk (OWASP API1,
2023). Until 14 October 2026 each route's stranger test was written by hand,
and nothing showed that all of them had one.

This builds one real world through the API, owned by brand A and creator A:
an open campaign, an application taken to an accepted deal, proof, a payment
marked sent, a dispute, an invitation, notifications, a phone, a block, a
rate-card package and a report. Then it walks every route the app serves
whose path names an object, fills the path from that world, and calls it as
an unrelated brand and an unrelated creator, each with a valid body, so a
refusal cannot be a validation error. Each must answer 403 or 404. Nothing
else: a 409 or a 422 would tell a stranger the object exists.

A route on the public list must instead answer the stranger 200, so the
list cannot outlive the truth. A route this test cannot fill fails, so a new
route is covered the day it is added.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import _leaf_routes
from app.core.rate_limit import limiter
from app.main import app
from app.modules.auth.models.passkey import Passkey
from app.modules.deal_memo.anchor_service import create_checkpoint
from tests.deal_flow import (
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import build_auth_session, create_account
from tests.step_up import ask_for_export, build_exports

SHA = "a" * 64

# Public by design (security.md section 2): who may read each, and why.
# Every other role must be refused like any stranger.
EVERYONE = frozenset({"brand", "creator"})
BRANDS = frozenset({"brand"})
PUBLIC: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    ("GET", "/api/v1/creators/by-handle/{handle}"): (
        EVERYONE,
        "a creator's Passport, once they publish it (D-036)",
    ),
    ("GET", "/api/v1/cities/{city}/figures"): (
        EVERYONE,
        "anonymous city figures (D-078)",
    ),
    ("GET", "/api/v1/campaigns/{campaign_id}"): (
        EVERYONE,
        "an open campaign, browsed by creators",
    ),
    ("GET", "/api/v1/brands/{brand_id}/reliability"): (
        EVERYONE,
        "a brand's payment record, read by creators before a deal",
    ),
    ("GET", "/api/v1/brands/{brand_id}/response-times"): (
        EVERYONE,
        "how fast a brand answers (D-077)",
    ),
    ("GET", "/api/v1/creators/{creator_id}/media-kit"): (
        BRANDS,
        "a published Passport as a media kit, for brands",
    ),
    ("GET", "/api/v1/creators/{creator_id}/delivery-record"): (
        BRANDS,
        "a creator's delivery record, read by brands before a deal",
    ),
    ("GET", "/api/v1/creators/{creator_id}/response-times"): (
        BRANDS,
        "how fast a creator answers (D-077), for brands",
    ),
    # Not a read, but open by design: any creator may apply to an open campaign.
    ("POST", "/api/v1/campaigns/{campaign_id}/applications"): (
        frozenset({"creator"}),
        "applying to an open campaign",
    ),
}

# Routes under /me name the caller's own things by kind, not another
# person's object: a stranger can only ever reach their own.
OWN_BY_CONSTRUCTION = {
    ("PUT", "/api/v1/creators/me/channels/{platform}"),
    ("DELETE", "/api/v1/creators/me/channels/{platform}"),
}

REASON = "The payment was marked sent on 8 September but nothing has reached my account."

# A valid body for every route that takes one, so a refusal is never a 422.
BODIES: dict[str, dict[str, Any]] = {
    "PackageUpdate": {"price_paise": 900_000},
    "SuspendIn": {"reason": "fraud", "note": "Checking a report."},
    "RestoreIn": {"note": "Checked: a mistake."},
    "ResolveReportIn": {"outcome": "dismissed", "note": "Looked genuine."},
    "LiftTakedownIn": {"note": "The order was set aside."},
    "CampaignUpdate": {"title": "Pongal sweets launch, extended"},
    "ApplicationCreate": {
        "pitch": "I run a Madurai street-food page with 12,000 followers."
    },
    "ApplicationReject": {"reason": "budget_mismatch"},
    "InvitationCreate": {"creator_id": "{creator_id}"},
    "InvitationDecline": {"reason": "timing"},
    "MemoCreate": {
        "deliverables": "3 Instagram reels.",
        "fee_amount_paise": 800_000,
        "content_due_on": "2026-12-31",
    },
    "MemoUpdate": {"deliverables": "4 Instagram reels."},
    "ChangeRequest": {"message": "Could the fee be 9,000?"},
    "RepeatCreate": {},
    "ProofUploadCreate": {"content_type": "image/png", "size_bytes": 1024, "sha256": SHA},
    "ProofCreate": {"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
    "MisreadMark": {"note": "The date it read is wrong."},
    "RevisionRequest": {"note": "Please add the product name."},
    "MarkPaidRequest": {"method": "upi", "reference": "412345678901"},
    "DisputeOpen": {"reason": REASON},
    "DisputeEntryCreate": {"note": "My bank statement shows nothing."},
    "DisputeClose": {"outcome": "resolved_paid"},
    "PasskeyRename": {"name": "Mine now"},
    "NameClearanceIn": {"note": "Checked the business behind it."},
}


def object_routes() -> list[APIRoute]:
    return sorted(
        (
            r
            for r in _leaf_routes(app.routes)
            if isinstance(r, APIRoute) and "{" in r.path
        ),
        key=lambda r: (r.path, sorted(r.methods)[0]),
    )


def method(route: APIRoute) -> str:
    return sorted(route.methods)[0]


@pytest.fixture
def world(client: TestClient, db: Session, clock) -> dict[str, Any]:
    """Everything brand A and creator A own, made through the API."""
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    def one(sql: str, **params: object) -> Any:
        return db.execute(text(sql), params).scalar_one()

    application_id = one("SELECT application_id FROM deal_memo WHERE id = :m", m=memo_id)
    campaign_id = one(
        "SELECT campaign_id FROM application WHERE id = :a", a=application_id
    )
    creator_id = one("SELECT id FROM creator WHERE account_id = :a", a=creator.account_id)
    brand_id = one("SELECT id FROM brand WHERE account_id = :a", a=brand.account_id)
    handle = one("SELECT handle FROM creator WHERE id = :c", c=creator_id)
    # Published, so the public routes are proven public, not merely refused.
    published = client.post(
        "/api/v1/creators/me/passport/publish", headers=creator.headers
    )
    assert published.status_code == 200, published.text

    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json=BODIES["ProofCreate"],
        headers=creator.headers,
    ).json()["id"]
    file_id = one(
        "INSERT INTO proof_file (deal_memo_id, uploader_account_id, storage_key, content_type,"
        " size_bytes, sha256, status, proof_id, attached_at, position)"
        " VALUES (:m, :a, 'proof-files/world', 'image/png', 1024, :sha, 'attached', :p, now(), 0)"
        " RETURNING id",
        m=memo_id,
        a=creator.account_id,
        sha=SHA,
        p=proof_id,
    )
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json=BODIES["MarkPaidRequest"],
        headers=brand.headers,
    )
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json=BODIES["DisputeOpen"],
        headers=creator.headers,
    )

    # An invitation on a second campaign, for the invitation routes.
    second = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Diwali hampers",
            "description": "Two reels on our festive hamper.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_000_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "2 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{second}/publish", headers=brand.headers)
    invitation_id = client.post(
        f"{CAMPAIGNS_URL}/{second}/invitations",
        json={"creator_id": str(creator_id)},
        headers=brand.headers,
    ).json()["id"]

    notification_id = one(
        "SELECT id FROM notification WHERE account_id = :a LIMIT 1", a=brand.account_id
    )
    device_id = client.put(
        "/api/v1/me/devices",
        json={"token": "w" * 64, "platform": "android"},
        headers=brand.headers,
    ).json()["id"]
    other_creator = creator_user(db, clock)
    other_creator_id = one(
        "SELECT id FROM creator WHERE account_id = :a", a=other_creator.account_id
    )
    block_id = client.post(
        "/api/v1/me/blocks",
        json={"creator_id": str(other_creator_id)},
        headers=brand.headers,
    ).json()["id"]
    package_id = client.post(
        "/api/v1/creators/me/packages",
        json={
            "platform": "instagram",
            "format": "reel",
            "title": "1 Instagram Reel",
            "description": "One reel, shot and edited by me.",
            "price_paise": 800_000,
            "delivery_days": 5,
            "usage_rights_days": 30,
            "position": 0,
        },
        headers=creator.headers,
    ).json()["id"]
    # A data export of the creator's own, built and ready (D-111).
    export_id = ask_for_export(client, creator.headers)
    # A passkey of the creator's own (D-113), as a row: its routes only need
    # one to exist, and passkeys are off in this test.
    passkey = Passkey(
        account_id=creator.account_id,
        credential_id=uuid.uuid4().bytes,
        public_key=bytes.fromhex("a10102"),
        sign_count=0,
        aaguid=uuid.UUID(int=0),
        backup_eligible=True,
        backup_state=True,
        name="My phone",
        created_at=clock.now,
        updated_at=clock.now,
    )
    db.add(passkey)
    # A live session of the creator's own (D-114), for ending one session.
    own_session = build_auth_session(
        db,
        account_id=creator.account_id,
        expires_at=clock.now + timedelta(days=30),
        created_at=clock.now,
        updated_at=clock.now,
    )
    db.add(own_session)
    db.flush()
    passkey_id = passkey.id
    session_id = own_session.family_id
    build_exports()
    report_id = client.post(
        "/api/v1/reports",
        json={
            "subject_kind": "creator",
            "subject_id": str(other_creator_id),
            "category": "fake_profile",
        },
        headers=brand.headers,
    ).json()["id"]
    city = one("SELECT city FROM creator WHERE id = :c", c=creator_id)
    # A takedown, of the other creator so the world's own stay visible (item 52).
    takedown_id = one(
        "INSERT INTO takedown (subject_kind, subject_id, owner_account_id, basis,"
        " report_id, received_at, due_at, withheld_at, withheld_by_account_id,"
        " preserved)"
        " SELECT 'creator', :c, :o, 'report', r.id, r.created_at, r.due_at,"
        " greatest(now(), r.created_at), :a, '{}' FROM report r WHERE r.id = :r"
        " RETURNING id",
        c=other_creator_id,
        o=other_creator.account_id,
        a=create_account(db, "admin").id,
        r=report_id,
    )

    # A second deal, approved but not yet paid, for the pay details.
    unpaid_creator = creator_user(db, clock)
    unpaid_memo_id = accepted_memo(client, brand, unpaid_creator)
    unpaid_proof = client.post(
        f"{MEMOS_URL}/{unpaid_memo_id}/proof",
        json=BODIES["ProofCreate"],
        headers=unpaid_creator.headers,
    ).json()["id"]
    client.post(
        f"{MEMOS_URL}/{unpaid_memo_id}/proof/{unpaid_proof}/approve",
        headers=brand.headers,
    )
    # The next day's checkpoint covers both deals, for the record's proof.
    create_checkpoint(db, india_date(clock.now) + timedelta(days=1))
    db.flush()

    ids = {
        "memo_id": memo_id,
        "application_id": application_id,
        "campaign_id": campaign_id,
        "creator_id": creator_id,
        "brand_id": brand_id,
        "handle": handle,
        "proof_id": proof_id,
        "file_id": file_id,
        "invitation_id": invitation_id,
        "notification_id": notification_id,
        "device_id": device_id,
        "block_id": block_id,
        "package_id": package_id,
        "report_id": report_id,
        "export_id": export_id,
        "passkey_id": passkey_id,
        "session_id": session_id,
        "takedown_id": takedown_id,
        "account_id": brand.account_id,
        "city": city,
        "unpaid_memo_id": unpaid_memo_id,
        "platform": "instagram",
    }
    assert all(value is not None for value in ids.values()), ids
    return {
        "ids": {k: str(v) for k, v in ids.items()},
        "brand": brand,
        "creator": creator,
    }


def fill(route: APIRoute, ids: dict[str, str]) -> str:
    path = route.path
    if "invitation" in path:
        # The invitation routes act on the invited application.
        path = path.replace("{application_id}", ids["invitation_id"])
    if path.endswith("/pay-details"):
        # Pay details close once a payment is marked sent: an unpaid deal.
        path = path.replace("{memo_id}", ids["unpaid_memo_id"])
    for name, value in ids.items():
        path = path.replace("{" + name + "}", value)
    assert "{" not in path, f"no object in the world for {route.path}; add one"
    return path


def body_for(route: APIRoute, ids: dict[str, str]) -> dict[str, Any] | None:
    if route.body_field is None:
        return None
    name = route.body_field.field_info.annotation.__name__
    assert name in BODIES, f"no valid body for {name} ({route.path}); add one to BODIES"
    return {
        key: (ids["creator_id"] if value == "{creator_id}" else value)
        for key, value in BODIES[name].items()
    }


@pytest.fixture
def strangers(db, clock) -> dict[str, User]:
    return {"brand": brand_user(db, clock), "creator": creator_user(db, clock)}


# Query parameters a route requires, so a refusal is never a 422.
QUERY = {"/api/v1/admin/accounts/{account_id}": {"reason": "Checking a report."}}


def call(client: TestClient, route: APIRoute, path: str, body, user: User):
    return client.request(
        method(route), path, json=body, params=QUERY.get(route.path), headers=user.headers
    )


def test_every_object_route_is_covered_by_this_test():
    """A guard: on an empty walk the test below would pass checking nothing."""
    routes = object_routes()
    known = PUBLIC.keys() | OWN_BY_CONSTRUCTION

    assert len(routes) >= 60
    assert known <= {(method(r), r.path) for r in routes}, (
        "a listed route no longer exists"
    )


def test_no_stranger_reaches_anyone_else_s_object(client, db, world, strangers):
    limiter.enabled = False
    try:
        leaks = []
        for route in object_routes():
            key = (method(route), route.path)
            if key in OWN_BY_CONSTRUCTION:
                continue
            path = fill(route, world["ids"])
            body = body_for(route, world["ids"])
            for role, stranger in strangers.items():
                # A refused call writes nothing; a leak would, and fails anyway.
                answer = call(client, route, path, body, stranger)
                open_to = PUBLIC[key][0] if key in PUBLIC else frozenset()
                expected = {200, 201} if role in open_to else {403, 404}
                if answer.status_code not in expected:
                    leaks.append(
                        f"{key[0]} {key[1]} as a stranger {role}: {answer.status_code}"
                    )
    finally:
        limiter.enabled = True

    assert leaks == []


def test_the_owners_can_read_what_the_strangers_cannot(client, world):
    """Proves the world's ids are real: every private read answers its owner."""
    owners = {"brand": world["brand"], "creator": world["creator"]}
    unread = []
    for route in object_routes():
        key = (method(route), route.path)
        if (
            key[0] != "GET"
            or (key in PUBLIC and PUBLIC[key][0] == EVERYONE)
            or "/admin/" in route.path
        ):
            continue
        path = fill(route, world["ids"])
        if not any(
            client.get(
                path, params=QUERY.get(route.path), headers=owner.headers
            ).status_code
            == 200
            for owner in owners.values()
        ):
            unread.append(key[1])

    assert unread == []


def test_admin_routes_answer_an_admin_but_no_stranger(client, db, clock, world):
    """The admin routes' "owner" is an admin; a real one reads the account."""
    account = create_account(db, "admin")
    db.commit()
    admin = User(account.id, "admin", clock)

    response = client.get(
        f"/api/v1/admin/accounts/{world['ids']['account_id']}",
        params=QUERY["/api/v1/admin/accounts/{account_id}"],
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    assert uuid.UUID(response.json()["id"]) == uuid.UUID(world["ids"]["account_id"])
