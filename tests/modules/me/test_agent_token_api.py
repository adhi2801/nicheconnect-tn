"""Tokens for assistants and agents (item 11, D-138), through the API.

Making one needs a code for exactly its scopes and tells the owner; a token
reaches only the routes of its scopes, never managing tokens or stepping
up; it stops when it expires, is revoked, or its owner logs out
everywhere, is suspended or deleted; and it shares its owner's limits.
Every route of the API is checked against the scopes in
tests/modules/auth/test_agent_scopes.py.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.main import app
from app.modules.admin import admin_service
from app.modules.auth import agent_tokens, erasure, step_up_service
from app.modules.auth import service as login
from app.modules.auth.exceptions import RoleNotAllowed
from app.modules.auth.models.account import Account
from app.modules.auth.models.agent_token import AgentToken
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.me import agent_token_service, export_service
from app.modules.notifications.models import Notification
from tests.deal_flow import (
    CAMPAIGNS_URL,
    MEMOS_URL,
    PITCH,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import create_account
from tests.query_counts import count_queries
from tests.step_up import STEP_UP_URL

TOKENS_URL = "/api/v1/me/agent-tokens"
ME_URL = "/api/v1/auth/me"
# A route `campaigns:read` reaches, for the tests of when a token works.
DISCOVER_URL = f"{CAMPAIGNS_URL}/discover"
PREFERENCES_URL = "/api/v1/me/notification-preferences"


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def phone_of(db, user: User) -> str:
    return db.get_one(Account, user.account_id).phone


def code_for(client, db, sender, user: User, scopes: list[str]) -> str:
    asked = client.post(
        STEP_UP_URL,
        json={"action": "create_agent_token", "scopes": scopes},
        headers=user.headers,
    )
    assert asked.status_code == 202, asked.text
    code = sender.last_code_for(phone_of(db, user))
    assert code is not None
    return code


def create(client, user: User, code: str | None, scopes: list[str], **fields):
    headers = user.headers if code is None else {**user.headers, "Step-Up-Code": code}
    body = {"name": "Claude on my laptop", "scopes": scopes, "expires_in_days": 30}
    return client.post(TOKENS_URL, json={**body, **fields}, headers=headers)


def make(client, db, sender, user: User, scopes: list[str], **fields) -> dict:
    made = create(
        client, user, code_for(client, db, sender, user, scopes), scopes, **fields
    )
    assert made.status_code == 201, made.text
    return made.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == code


# --- making one ---------------------------------------------------------------------


def test_a_token_is_made_with_a_code_for_its_scopes_and_shown_once(
    client, db, sender, creator, clock
):
    made = make(client, db, sender, creator, ["deals:read", "notes:write"])

    assert made["token"].startswith("nct_")
    assert made["scopes"] == ["deals:read", "notes:write"]
    assert made["expires_at"].startswith(
        (clock.now + timedelta(days=30)).date().isoformat()
    )
    assert made["last_used_at"] is None
    row = db.get_one(AgentToken, uuid.UUID(made["id"]))
    # Only the keyed hash is kept, never the token.
    assert row.token_hash == agent_tokens.hash_agent_token(made["token"])
    assert made["token"] not in row.token_hash
    listed = client.get(TOKENS_URL, headers=creator.headers).json()["items"]
    assert [item["id"] for item in listed] == [made["id"]]
    assert "token" not in listed[0]


def test_without_a_code_no_token_is_made(client, db, creator):
    response = create(client, creator, None, ["deals:read"])

    assert_problem(response, 401, "step_up_required")
    assert (
        db.scalar(
            select(func.count())
            .select_from(AgentToken)
            .where(AgentToken.account_id == creator.account_id)
        )
        == 0
    )


def test_a_code_for_read_only_scopes_cannot_make_a_token_that_writes(
    client, db, sender, creator
):
    code = code_for(client, db, sender, creator, ["deals:read"])

    response = create(client, creator, code, ["deals:read", "notes:write"])

    assert_problem(response, 400, "step_up_code_invalid")


def test_the_same_scopes_in_another_order_are_the_same_change(
    client, db, sender, creator
):
    code = code_for(client, db, sender, creator, ["notes:write", "deals:read"])

    response = create(client, creator, code, ["deals:read", "notes:write", "deals:read"])

    assert response.status_code == 201, response.text
    assert response.json()["scopes"] == ["deals:read", "notes:write"]


def test_the_owner_is_told_and_cannot_mute_it(client, db, sender, creator):
    made = make(client, db, sender, creator, ["campaigns:read"])

    [notice] = db.scalars(
        select(Notification).where(
            Notification.account_id == creator.account_id,
            Notification.notification_type == "agent_token_created",
        )
    ).all()
    assert notice.details["agent_token_id"] == made["id"]
    assert notice.details["scopes"] == ["campaigns:read"]
    assert made["token"] not in str(notice.details)
    muted = client.put(
        PREFERENCES_URL,
        json={
            "quiet_from": None,
            "quiet_until": None,
            "digest": "off",
            "digest_hour": 19,
            "muted_types": ["agent_token_created"],
        },
        headers=creator.headers,
    )
    assert_problem(muted, 422, "urgent_type_not_mutable")


def test_an_admin_cannot_make_one(client, db, sender, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)

    asked = client.post(
        STEP_UP_URL,
        json={"action": "create_agent_token", "scopes": ["deals:read"]},
        headers=admin.headers,
    )

    assert_problem(asked, 403, "role_not_allowed")


@pytest.mark.parametrize(
    "fields",
    [
        {"expires_in_days": 91},
        {"expires_in_days": 0},
        {"scopes": []},
        {"scopes": ["payments:write"]},
        {"name": ""},
        {"name": "x" * 61},
        {"name": "line\nbreak"},
    ],
)
def test_a_token_outside_the_limits_is_refused(client, creator, fields):
    body = {"name": "Claude", "scopes": ["deals:read"], "expires_in_days": 30, **fields}

    response = client.post(
        TOKENS_URL, json=body, headers={**creator.headers, "Step-Up-Code": "123456"}
    )

    assert response.status_code == 422, response.text


# --- what a token reaches -------------------------------------------------------------


def test_the_answer_carrying_a_token_is_never_cached(client, db, sender, creator):
    scopes = ["deals:read"]
    code = code_for(client, db, sender, creator, scopes)

    response = create(client, creator, code, scopes)

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"


def test_a_token_reaches_its_scope(client, db, sender, creator):
    made = make(client, db, sender, creator, ["campaigns:read"])

    response = client.get(DISCOVER_URL, headers=bearer(made["token"]))

    assert response.status_code == 200, response.text


def test_a_token_never_reads_payment_records_the_phone_or_accepts(
    client, db, sender, brand, creator
):
    """Found by the independent review of item 11 on 27 October 2026."""
    every = [
        "deals:read",
        "campaigns:read",
        "applications:write",
        "notes:write",
        "alerts:write",
    ]
    memo_id = accepted_memo(client, brand, creator)
    # The brand's one campaign, made for the deal.
    [campaign] = client.get(CAMPAIGNS_URL, headers=brand.headers).json()["items"]
    campaign_id = campaign["id"]
    for_brand = bearer(make(client, db, sender, brand, every)["token"])
    for_creator = bearer(make(client, db, sender, creator, every)["token"])

    refused = [
        client.get(ME_URL, headers=for_creator),
        client.get(f"{MEMOS_URL}/{memo_id}/record", headers=for_creator),
        client.get(f"{CAMPAIGNS_URL}/{campaign_id}/report", headers=for_brand),
        client.get(f"{CAMPAIGNS_URL}/{campaign_id}/report.csv", headers=for_brand),
        client.post(
            f"/api/v1/applications/{uuid.uuid4()}/accept-invitation", headers=for_creator
        ),
    ]

    for response in refused:
        assert_problem(response, 403, "agent_scope_missing")


def test_a_token_reads_deals_only_with_deals_read(client, db, sender, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    reader = make(client, db, sender, creator, ["deals:read"])["token"]
    other = make(client, db, sender, creator, ["campaigns:read"])["token"]

    assert client.get(f"{MEMOS_URL}/{memo_id}", headers=bearer(reader)).status_code == 200
    assert_problem(
        client.get(f"{MEMOS_URL}/{memo_id}", headers=bearer(other)),
        403,
        "agent_scope_missing",
    )


def test_a_token_writes_a_note_only_with_notes_write(client, db, sender, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    reader = make(client, db, sender, creator, ["deals:read"])["token"]
    writer = make(client, db, sender, creator, ["notes:write"])["token"]
    note = {"body": "Shooting the first reel on Friday."}

    assert_problem(
        client.post(f"{MEMOS_URL}/{memo_id}/notes", json=note, headers=bearer(reader)),
        403,
        "agent_scope_missing",
    )
    written = client.post(
        f"{MEMOS_URL}/{memo_id}/notes", json=note, headers=bearer(writer)
    )
    assert written.status_code == 201, written.text


def test_a_token_applies_to_a_campaign_with_applications_write(
    client, db, sender, brand, creator
):
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
    agent = make(client, db, sender, creator, ["applications:write"])["token"]

    applied = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=bearer(agent),
    )

    assert applied.status_code == 201, applied.text


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        # Managing tokens: only the person.
        ("GET", TOKENS_URL, None),
        (
            "POST",
            TOKENS_URL,
            {"name": "x", "scopes": ["deals:read"], "expires_in_days": 1},
        ),
        # Stepping up, so no token can ever prove a risky change.
        ("POST", STEP_UP_URL, {"action": "log_out_everywhere"}),
        # Money, identity and the account's control.
        ("GET", "/api/v1/creators/me/upi", None),
        ("GET", "/api/v1/payments/mine", None),
        ("GET", "/api/v1/me/sessions", None),
        ("POST", "/api/v1/me/exports", None),
        ("GET", "/api/v1/me/deletion", None),
        ("GET", "/api/v1/me/passkeys", None),
    ],
)
def test_a_token_with_every_scope_never_reaches_these(
    client, db, sender, creator, method, url, body
):
    every = [
        "deals:read",
        "campaigns:read",
        "applications:write",
        "notes:write",
        "alerts:write",
    ]
    token = make(client, db, sender, creator, every)["token"]

    response = client.request(method, url, json=body, headers=bearer(token))

    assert_problem(response, 403, "agent_scope_missing")


# --- when a token stops --------------------------------------------------------------


def test_a_token_stops_when_it_expires(client, db, sender, creator, clock):
    token = make(client, db, sender, creator, ["campaigns:read"], expires_in_days=1)[
        "token"
    ]
    clock.advance(timedelta(days=1))

    assert_problem(client.get(DISCOVER_URL, headers=bearer(token)), 401, "invalid_token")


def test_an_unknown_token_is_refused_like_an_expired_one(client):
    response = client.get(DISCOVER_URL, headers=bearer(agent_tokens.new_agent_token()))

    assert_problem(response, 401, "invalid_token")
    assert response.headers["www-authenticate"] == "Bearer"


def test_the_owner_revokes_a_token_and_it_stops(client, db, sender, creator):
    made = make(client, db, sender, creator, ["campaigns:read"])

    revoked = client.delete(f"{TOKENS_URL}/{made['id']}", headers=creator.headers)

    assert revoked.status_code == 204, revoked.text
    assert_problem(
        client.get(DISCOVER_URL, headers=bearer(made["token"])), 401, "invalid_token"
    )
    assert client.get(TOKENS_URL, headers=creator.headers).json()["items"] == []
    assert_problem(
        client.delete(f"{TOKENS_URL}/{made['id']}", headers=creator.headers),
        404,
        "agent_token_not_found",
    )


def test_nobody_revokes_another_persons_token(client, db, sender, creator, brand):
    made = make(client, db, sender, creator, ["campaigns:read"])

    response = client.delete(f"{TOKENS_URL}/{made['id']}", headers=brand.headers)

    assert_problem(response, 404, "agent_token_not_found")
    assert client.get(DISCOVER_URL, headers=bearer(made["token"])).status_code == 200


def test_logging_out_everywhere_ends_every_token(client, db, sender, creator, clock):
    token = make(client, db, sender, creator, ["campaigns:read"])["token"]

    login.logout_all_sessions(db, creator.account_id, clock.now)
    db.flush()

    assert_problem(client.get(DISCOVER_URL, headers=bearer(token)), 401, "invalid_token")


def test_a_suspended_owners_token_stops(client, db, sender, creator, clock):
    token = make(client, db, sender, creator, ["campaigns:read"])["token"]
    account = db.get_one(Account, creator.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "fake_profile"
    db.flush()

    assert_problem(
        client.get(DISCOVER_URL, headers=bearer(token)), 403, "account_suspended"
    )


def test_suspending_revokes_every_token_so_restoring_brings_none_back(
    client, db, sender, creator, clock
):
    """Found by the independent review of item 11 on 27 October 2026."""
    token = make(client, db, sender, creator, ["campaigns:read"])["token"]
    admin = create_account(db, "admin")

    admin_service.suspend(
        db,
        admin,
        creator.account_id,
        reason="fake_profile",
        note="Taken over",
        now=clock.now,
    )
    admin_service.restore(db, admin, creator.account_id, note="Owner back", now=clock.now)

    assert_problem(client.get(DISCOVER_URL, headers=bearer(token)), 401, "invalid_token")


def test_a_deleted_owners_token_stops(client, db, sender, creator, clock):
    token = make(client, db, sender, creator, ["campaigns:read"])["token"]
    account = db.get_one(Account, creator.account_id)
    # Asked 30 days ago, as every deletion is before it takes effect (D-122).
    account.deletion_requested_at = clock.now - timedelta(days=30)
    account.deletion_takes_effect_at = clock.now
    erasure.empty_identity(db, account, erasure.lock_profile(db, account), clock.now)
    db.flush()

    # A route with no guard of its own for a deleted account, unlike /auth/me.
    response = client.get(f"{CAMPAIGNS_URL}/discover", headers=bearer(token))
    assert_problem(response, 401, "invalid_token")
    assert response.headers["www-authenticate"] == "Bearer"


def test_an_admin_is_refused_at_each_layer(db, clock):
    admin = create_account(db, "admin")

    with pytest.raises(RoleNotAllowed):
        agent_token_service.create(
            db, admin, "Claude", ["deals:read"], 30, None, clock.now
        )
    with pytest.raises(RoleNotAllowed):
        step_up_service.request_code(
            db, admin, "create_agent_token", "deals:read", clock.now
        )


def test_the_export_lists_every_token_without_its_hash(
    client, db, sender, creator, clock
):
    made = make(client, db, sender, creator, ["campaigns:read"])
    client.delete(f"{TOKENS_URL}/{made['id']}", headers=creator.headers)
    account = db.get_one(Account, creator.account_id)

    [section] = [
        found
        for found in export_service.collect_sections(db, account, clock.now)
        if found.table == "agent_token"
    ]

    [record] = section.records
    assert record["id"] == made["id"]
    assert record["revoked_at"] is not None
    assert "token_hash" not in record


def test_erasing_the_account_removes_its_tokens(client, db, sender, creator):
    make(client, db, sender, creator, ["campaigns:read"])

    erasure.erase_for_account(db, db.get_one(Account, creator.account_id))

    assert (
        db.scalar(
            select(func.count())
            .select_from(AgentToken)
            .where(AgentToken.account_id == creator.account_id)
        )
        == 0
    )


# --- use, and limits --------------------------------------------------------------------


def test_last_use_is_written_at_most_once_a_minute(client, db, sender, creator, clock):
    made = make(client, db, sender, creator, ["campaigns:read"])
    first = clock.now

    client.get(DISCOVER_URL, headers=bearer(made["token"]))
    clock.advance(timedelta(seconds=30))
    client.get(DISCOVER_URL, headers=bearer(made["token"]))
    row = db.get_one(AgentToken, uuid.UUID(made["id"]))
    db.refresh(row)
    assert row.last_used_at == first

    clock.advance(timedelta(seconds=30))
    client.get(DISCOVER_URL, headers=bearer(made["token"]))
    db.refresh(row)
    assert row.last_used_at == first + timedelta(minutes=1)


def test_a_refused_call_is_never_shown_as_a_use(client, db, sender, creator):
    made = make(client, db, sender, creator, ["campaigns:read"])

    refused = client.get("/api/v1/me/sessions", headers=bearer(made["token"]))

    assert_problem(refused, 403, "agent_scope_missing")
    row = db.get_one(AgentToken, uuid.UUID(made["id"]))
    db.refresh(row)
    assert row.last_used_at is None


def test_a_token_shares_its_owners_rate_limit(client, db, sender, creator):
    token = make(client, db, sender, creator, ["campaigns:read"])["token"]
    for _ in range(60):
        assert client.get(DISCOVER_URL, headers=creator.headers).status_code == 200

    assert client.get(DISCOVER_URL, headers=bearer(token)).status_code == 429


def test_the_list_is_one_query_however_long(client, db, sender, creator, clock):
    for scopes in (["deals:read"], ["campaigns:read"], ["alerts:write"]):
        make(client, db, sender, creator, scopes)

    with count_queries() as statements:
        listed = client.get(TOKENS_URL, headers=creator.headers)

    assert len(listed.json()["items"]) == 3
    token_reads = [s for s in statements if "FROM agent_token" in s]
    assert len(token_reads) == 1, token_reads


def test_the_list_pages_newest_first(client, db, sender, creator, clock):
    ids = []
    for _ in range(3):
        ids.append(make(client, db, sender, creator, ["deals:read"])["id"])
        clock.advance(timedelta(seconds=1))

    first = client.get(TOKENS_URL, params={"limit": 2}, headers=creator.headers).json()
    second = client.get(
        TOKENS_URL,
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=creator.headers,
    ).json()

    assert [item["id"] for item in first["items"] + second["items"]] == ids[::-1]
    assert second["next_cursor"] is None
