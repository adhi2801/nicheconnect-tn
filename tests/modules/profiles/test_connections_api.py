"""Connected Instagram and YouTube accounts, through the API (item 29, D-134).

The rules worth proving: a sign-in works once, for the account and platform
that began it; the account it reaches belongs to one creator; tokens are
sealed and never leave; disconnecting is always allowed; and Meta's
callbacks act only on Meta's signature.
"""

import base64
import hashlib
import json
import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.me import export_service
from app.modules.profiles.connection_models import (
    ConnectedAccount,
    ConnectionAttempt,
    PlatformDeletionRequest,
)
from app.modules.profiles.connection_router import CONNECT_LIMIT
from app.modules.profiles.meta_signed_request import sign
from tests.deal_flow import User, brand_user, creator_user
from tests.modules.admin.test_takedowns_api import creator_id_of
from tests.modules.profiles.connections_world import (
    META_SECRET,
    REDIRECT_BASE,
    profile,
)

URL = "/api/v1/creators/me/connections"
META = "/api/v1/platforms/meta"


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def start(client, user: User, platform: str = "instagram") -> dict[str, str]:
    response = client.post(f"{URL}/{platform}/start", headers=user.headers)
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["authorize_url"]).query)
    return {key: values[0] for key, values in query.items()}


def complete(
    client, user: User, state: str, code: str = "good-code", platform="instagram"
):
    return client.post(
        f"{URL}/{platform}/complete",
        json={"code": code, "state": state},
        headers=user.headers,
    )


def connected(client, user: User, fakes, platform="instagram", code="good-code", **who):
    fakes[platform].profiles[code] = profile(**who)
    response = complete(
        client, user, start(client, user, platform)["state"], code, platform
    )
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def form(signed_request: str) -> dict:
    return {
        "content": f"signed_request={signed_request}".encode(),
        "headers": {"content-type": "application/x-www-form-urlencoded"},
    }


# --- switched off ----------------------------------------------------------------


def test_switched_off_nothing_starts(client, creator):
    assert_problem(
        client.post(f"{URL}/instagram/start", headers=creator.headers),
        503,
        "connections_unavailable",
    )
    assert_problem(complete(client, creator, "any-state"), 503, "connections_unavailable")


# --- connecting ------------------------------------------------------------------


def test_a_creator_connects_instagram(client, db, creator, platforms):
    platforms["instagram"].profiles["good-code"] = profile()
    query = start(client, creator)

    response = complete(client, creator, query["state"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert {
        k: body[k] for k in ("platform", "handle", "status", "verified_followers")
    } == {
        "platform": "instagram",
        "handle": "priya.eats",
        "status": "active",
        "verified_followers": 24_000,
    }
    assert query["redirect_uri"] == f"{REDIRECT_BASE}/instagram"
    assert "code_challenge" not in query  # Instagram Login documents no PKCE
    assert client.get(URL, headers=creator.headers).json() == [body]
    row = db.scalars(select(ConnectedAccount)).first()
    assert row.notice_version == "connect-v1"
    # Sealed: the token itself is nowhere in the row.
    assert b"access-for-good-code" not in row.access_token_sealed


def test_youtube_uses_pkce_and_the_verifier_matches_its_challenge(
    client,
    creator,
    platforms,
):
    platforms["youtube"].profiles["yt-code"] = profile("UCabc", "Priya Eats", 1200)
    query = start(client, creator, "youtube")

    response = complete(client, creator, query["state"], "yt-code", "youtube")

    assert response.status_code == 200, response.text
    ((_, verifier),) = platforms["youtube"].exchanged
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert query["code_challenge"] == challenge


def test_the_state_is_kept_only_as_its_hash(client, db, creator, platforms):
    query = start(client, creator)

    attempt = db.scalars(select(ConnectionAttempt)).first()
    assert attempt.state_sha256 == hashlib.sha256(query["state"].encode()).hexdigest()
    assert query["state"] not in attempt.state_sha256


def test_a_state_works_once(client, creator, platforms):
    platforms["instagram"].profiles["good-code"] = profile()
    state = start(client, creator)["state"]
    assert complete(client, creator, state).status_code == 200

    assert_problem(complete(client, creator, state), 409, "connection_attempt_invalid")


def test_another_accounts_state_is_refused(client, db, clock, creator, platforms):
    platforms["instagram"].profiles["good-code"] = profile()
    thief = creator_user(db, clock)
    state = start(client, creator)["state"]

    assert_problem(complete(client, thief, state), 409, "connection_attempt_invalid")
    assert client.get(URL, headers=thief.headers).json() == []
    # The owner's attempt is untouched by the refusal.
    assert complete(client, creator, state).status_code == 200


def test_a_state_works_only_on_its_platform(client, creator, platforms):
    platforms["youtube"].profiles["good-code"] = profile()
    state = start(client, creator, "instagram")["state"]

    assert_problem(
        complete(client, creator, state, platform="youtube"),
        409,
        "connection_attempt_invalid",
    )


def test_a_state_expires_after_ten_minutes(client, clock, creator, platforms):
    platforms["instagram"].profiles["good-code"] = profile()
    state = start(client, creator)["state"]
    clock.advance(timedelta(minutes=10))

    assert_problem(complete(client, creator, state), 409, "connection_attempt_invalid")


def test_an_unknown_state_is_refused(client, creator, platforms):
    assert_problem(
        complete(client, creator, "made-up"), 409, "connection_attempt_invalid"
    )


def test_a_code_the_platform_refuses(client, creator, platforms):
    state = start(client, creator)["state"]

    assert_problem(complete(client, creator, state, "bad-code"), 409, "platform_refused")


def test_a_platform_that_does_not_answer(client, creator, platforms):
    platforms["instagram"].unavailable = True
    state = start(client, creator)["state"]

    response = complete(client, creator, state)

    assert_problem(response, 503, "platform_unavailable")
    assert response.headers["Retry-After"] == "60"


def test_one_channel_belongs_to_one_creator(client, db, clock, creator, platforms):
    connected(client, creator, platforms, user_id="1784")
    other = creator_user(db, clock)
    platforms["instagram"].profiles["other-code"] = profile(user_id="1784")

    response = complete(client, other, start(client, other)["state"], "other-code")

    assert_problem(response, 409, "channel_already_connected")
    assert client.get(URL, headers=other.headers).json() == []
    assert platforms["instagram"].revoked == ["access-for-other-code"]


def test_connecting_again_replaces_the_connection(client, db, creator, platforms):
    connected(client, creator, platforms, code="first", user_id="1", handle="old.name")

    body = connected(
        client, creator, platforms, code="second", user_id="2", handle="new.name"
    )

    assert body["handle"] == "new.name"
    assert [c["handle"] for c in client.get(URL, headers=creator.headers).json()] == [
        "new.name"
    ]


def test_a_hidden_count_reads_null_never_zero(client, creator, platforms):
    body = connected(client, creator, platforms, "youtube", followers=None)

    assert (body["verified_followers"], body["verified_as_of"]) == (None, None)


def test_brands_connect_nothing(client, db, clock, platforms):
    brand = brand_user(db, clock)

    assert client.post(f"{URL}/instagram/start", headers=brand.headers).status_code == 403


def test_connecting_needs_a_login(client):
    assert client.post(f"{URL}/instagram/start").status_code == 401
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "body",
    [{"code": "", "state": "s"}, {"code": "c"}, {"code": "c", "state": "s", "x": 1}],
)
def test_a_bad_completion_is_refused(client, creator, platforms, body):
    response = client.post(
        f"{URL}/instagram/complete", json=body, headers=creator.headers
    )

    assert response.status_code == 422


def test_an_unknown_platform_is_refused(client, creator, platforms):
    assert client.post(f"{URL}/tiktok/start", headers=creator.headers).status_code == 422


def test_starting_is_rate_limited(client, creator, platforms):
    for _ in range(int(CONNECT_LIMIT.split()[0])):
        assert (
            client.post(f"{URL}/instagram/start", headers=creator.headers).status_code
            == 200
        )

    assert (
        client.post(f"{URL}/instagram/start", headers=creator.headers).status_code == 429
    )


# --- disconnecting -----------------------------------------------------------------


def test_disconnecting_deletes_and_revokes(client, db, creator, platforms):
    connected(client, creator, platforms, "youtube", code="yt")

    response = client.delete(f"{URL}/youtube", headers=creator.headers)

    assert response.status_code == 204
    assert client.get(URL, headers=creator.headers).json() == []
    assert platforms["youtube"].revoked == ["access-for-yt"]
    assert_problem(
        client.delete(f"{URL}/youtube", headers=creator.headers),
        404,
        "connection_not_found",
    )


def test_disconnecting_works_with_the_switch_off(client, creator, platforms, monkeypatch):
    connected(client, creator, platforms)
    monkeypatch.setattr(settings, "platform_connections_enabled", False)

    assert client.delete(f"{URL}/instagram", headers=creator.headers).status_code == 204
    assert platforms["instagram"].revoked == []  # nothing is called while off


# --- tokens never leave --------------------------------------------------------------


def test_no_answer_export_or_log_holds_a_token(
    client,
    db,
    clock,
    creator,
    platforms,
    caplog,
):
    caplog.set_level(logging.DEBUG)
    body = connected(client, creator, platforms, "youtube", code="yt")
    listed = client.get(URL, headers=creator.headers).text

    exported = export_service.build_export(
        db, db.get_one(Account, creator.account_id), clock.now
    )
    text = json.dumps(exported, default=str)

    for leak in ("access-for-yt", "refresh-for-yt"):
        assert leak not in json.dumps(body) + listed + text + caplog.text
    (section,) = exported["data"]["connected_accounts"]
    assert section["handle"] == body["handle"]
    assert not any("token" in key for key in section)


# --- Meta's callbacks ----------------------------------------------------------------


def signed(user_id: str, secret: str = META_SECRET) -> str:
    return sign({"algorithm": "HMAC-SHA256", "user_id": user_id, "issued_at": 1}, secret)


def test_meta_deletion_removes_the_connection_and_answers_its_status(
    client,
    db,
    clock,
    creator,
    platforms,
):
    connected(client, creator, platforms, user_id="1784")
    other = creator_user(db, clock)
    platforms["instagram"].profiles["kept"] = profile(user_id="9999")
    complete(client, other, start(client, other)["state"], "kept")

    response = client.post(f"{META}/data-deletion", **form(signed("1784")))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"] == f"{REDIRECT_BASE}/meta-deletion/{body['confirmation_code']}"
    assert client.get(URL, headers=creator.headers).json() == []
    assert len(client.get(URL, headers=other.headers).json()) == 1
    status = client.get(f"{META}/data-deletion/{body['confirmation_code']}")
    assert status.status_code == 200, status.text
    assert (status.json()["status"], status.json()["removed"]) == ("done", 1)


def test_meta_deletion_for_someone_we_never_held_still_answers(client, platforms):
    response = client.post(f"{META}/data-deletion", **form(signed("424242")))

    assert response.status_code == 200, response.text
    code = response.json()["confirmation_code"]
    assert client.get(f"{META}/data-deletion/{code}").json()["removed"] == 0


@pytest.mark.parametrize(
    "request_text",
    ["", "no-dot", "abc.def", "{wrong}", "@@@.@@@"],
)
def test_a_forged_meta_call_deletes_nothing(client, creator, platforms, request_text):
    connected(client, creator, platforms, user_id="1784")

    assert_problem(
        client.post(f"{META}/data-deletion", **form(request_text)),
        400,
        "invalid_signed_request",
    )
    assert len(client.get(URL, headers=creator.headers).json()) == 1


def test_a_call_signed_with_another_secret_deletes_nothing(client, creator, platforms):
    connected(client, creator, platforms, user_id="1784")

    response = client.post(f"{META}/data-deletion", **form(signed("1784", "not-ours")))

    assert_problem(response, 400, "invalid_signed_request")
    assert len(client.get(URL, headers=creator.headers).json()) == 1


def test_meta_deauthorize_removes_the_connection(client, creator, platforms):
    connected(client, creator, platforms, user_id="1784")

    response = client.post(f"{META}/deauthorize", **form(signed("1784")))

    assert response.status_code == 204
    assert client.get(URL, headers=creator.headers).json() == []


def test_meta_callbacks_without_an_app_answer_unavailable(client):
    assert_problem(
        client.post(f"{META}/data-deletion", **form(signed("1"))),
        503,
        "connections_unavailable",
    )


def test_an_unknown_confirmation_code_is_not_found(client):
    assert_problem(
        client.get(f"{META}/data-deletion/nothing-here"),
        404,
        "deletion_request_not_found",
    )


def test_deleting_the_account_erases_its_connection(
    client, db, clock, creator, platforms
):
    from app.modules.profiles import connection_service

    connected(client, creator, platforms)
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    ).one()
    assert creator_id_of(db, creator) == str(creator_id)

    connection_service.erase_for_creator(db, creator_id)

    assert db.scalars(select(ConnectedAccount)).first() is None
    assert db.scalars(select(PlatformDeletionRequest)).first() is None
