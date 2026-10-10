"""How accounts arrive, invite codes, and sign-ups by source (D-080).

Sign-ups go through the real login, with the fake code sender, because the
rule that matters most lives there: arrival is written only by the login
that creates the account.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.attribution_service import new_code, normalise_code
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.attribution import CODE_ALPHABET, AccountAttribution
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import create_access_token
from tests.factories import FIXED_NOW, create_account, fake_phone


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def sender() -> FakeOtpSender:
    return FakeOtpSender()


@pytest.fixture
def client(db, clock, sender) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    app.dependency_overrides[get_otp_sender] = lambda: sender
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def sign_up(
    client: TestClient,
    sender: FakeOtpSender,
    *,
    role: str = "creator",
    phone: str | None = None,
    arrival: dict | None = None,
) -> dict:
    phone = phone or fake_phone()
    # Many people sign up from one test address; the login's own limits are
    # tested in test_otp_api.py, not here.
    limiter.reset()
    assert (
        client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 202
    )
    body: dict = {"phone": phone, "code": sender.last_code_for(phone), "role": role}
    if arrival is not None:
        body["arrival"] = arrival
    response = client.post("/api/v1/auth/otp/verify", json=body)
    assert response.status_code == 200, response.text
    tokens = response.json()
    return {
        "account_id": tokens["account"]["id"],
        "is_new": tokens["account"]["is_new"],
        "phone": phone,
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


def arrival_of(db, account_id: str) -> AccountAttribution | None:
    return db.scalars(
        select(AccountAttribution).where(AccountAttribution.account_id == account_id)
    ).first()


def code_of(client: TestClient, user: dict) -> str:
    response = client.get("/api/v1/me/invite-code", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()["code"]


# --- recorded once, at sign-up -------------------------------------------------------------


def test_a_new_account_records_where_it_came_from(client, db, sender):
    user = sign_up(
        client, sender, arrival={"source": "instagram", "campaign_tag": "codissia-oct"}
    )

    found = arrival_of(db, user["account_id"])
    assert (found.source, found.campaign_tag, found.invite_code_id) == (
        "instagram",
        "codissia-oct",
        None,
    )


def test_saying_nothing_is_recorded_as_not_given(client, db, sender):
    user = sign_up(client, sender)

    assert arrival_of(db, user["account_id"]).source == "not_given"


def test_a_returning_login_cannot_rewrite_how_it_arrived(client, db, clock, sender):
    first = sign_up(client, sender, arrival={"source": "whatsapp"})
    clock.advance(timedelta(hours=1))  # past the wait between codes

    again = sign_up(client, sender, phone=first["phone"], arrival={"source": "event"})

    assert again["is_new"] is False
    assert arrival_of(db, first["account_id"]).source == "whatsapp"


def test_an_invite_code_links_the_new_account_to_its_inviter(client, db, sender):
    inviter = sign_up(client, sender, role="brand")
    code = code_of(client, inviter)

    joined = sign_up(client, sender, arrival={"invite_code": code, "source": "instagram"})

    found = arrival_of(db, joined["account_id"])
    assert found.source == "invite"  # a valid code outranks what else was said
    assert found.invite_code_id is not None


def test_a_code_is_found_however_it_is_typed(client, db, sender):
    code = code_of(client, sign_up(client, sender))
    typed = f" {code[:4].lower()}-{code[4:]} "

    joined = sign_up(client, sender, arrival={"invite_code": typed})

    assert arrival_of(db, joined["account_id"]).source == "invite"


def test_an_unknown_code_never_blocks_sign_up(client, db, sender):
    joined = sign_up(
        client, sender, arrival={"invite_code": "ZZZZZZZZ", "source": "event"}
    )

    found = arrival_of(db, joined["account_id"])
    assert (found.source, found.invite_code_id) == ("event", None)


@pytest.mark.parametrize(
    "arrival",
    [
        {"source": "invite"},  # only a valid code makes an invitation
        {"source": "not_given"},
        {"source": "billboard"},
        {"campaign_tag": "Has Capitals"},
        {"invite_code": "<script>"},
        {"surprise": "field"},
    ],
)
def test_a_bad_arrival_is_refused_before_anything_happens(client, sender, arrival):
    phone = fake_phone()
    client.post("/api/v1/auth/otp/request", json={"phone": phone})
    response = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "phone": phone,
            "code": sender.last_code_for(phone),
            "role": "creator",
            "arrival": arrival,
        },
    )

    assert response.status_code == 422


# --- my code and my invites ------------------------------------------------------------------


def test_my_code_is_made_once_and_stays_the_same(client, sender):
    user = sign_up(client, sender)

    first, second = code_of(client, user), code_of(client, user)

    assert first == second
    assert len(first) == 8 and set(first) <= set(CODE_ALPHABET)


def test_an_inviter_sees_counts_and_never_who(client, sender):
    inviter = sign_up(client, sender)
    code = code_of(client, inviter)
    for role in ("brand", "brand", "creator"):
        sign_up(client, sender, role=role, arrival={"invite_code": code})
    sign_up(client, sender)  # joined without the code

    response = client.get("/api/v1/me/invites", headers=inviter["headers"])

    assert response.json() == {"brands": 2, "creators": 1}


def test_nobody_counts_anyone_elses_invites(client, sender):
    inviter, other = sign_up(client, sender), sign_up(client, sender)
    sign_up(client, sender, arrival={"invite_code": code_of(client, inviter)})

    response = client.get("/api/v1/me/invites", headers=other["headers"])

    assert response.json() == {"brands": 0, "creators": 0}


@pytest.mark.parametrize("path", ["/api/v1/me/invite-code", "/api/v1/me/invites"])
def test_an_admin_has_no_invitations(client, db, clock, path):
    admin = create_account(db, "admin")
    token, _ = create_access_token(admin.id, "admin", clock.now)

    response = client.get(path, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/v1/me/invite-code", "/api/v1/me/invites"])
def test_it_needs_a_login(client, path):
    assert client.get(path).status_code == 401


# --- sign-ups by source --------------------------------------------------------------------


def admin_headers(db, clock) -> dict:
    admin = create_account(db, "admin")
    token, _ = create_access_token(admin.id, "admin", clock.now)
    return {"Authorization": f"Bearer {token}"}


def test_an_admin_sees_sign_ups_by_week_source_and_role(client, db, clock, sender):
    for source in ("instagram", "instagram", "event"):
        sign_up(client, sender, arrival={"source": source})
    sign_up(client, sender, role="brand", arrival={"source": "instagram"})

    rows = client.get("/api/v1/admin/signups", headers=admin_headers(db, clock)).json()

    this_week = {
        (row["source"], row["role"]): row["accounts"]
        for row in rows
        if row["week_starting"] == rows[0]["week_starting"]
    }
    assert this_week[("instagram", "creator")] >= 2
    assert this_week[("instagram", "brand")] >= 1
    assert this_week[("event", "creator")] >= 1
    assert all(
        set(row) == {"week_starting", "source", "role", "accounts"} for row in rows
    )


def test_weeks_start_on_monday_in_tamil_nadu(client, db, clock, sender):
    sign_up(client, sender)

    rows = client.get("/api/v1/admin/signups", headers=admin_headers(db, clock)).json()

    assert datetime.fromisoformat(rows[0]["week_starting"]).weekday() == 0


def test_sign_ups_are_hidden_from_everyone_but_admins(client, sender):
    user = sign_up(client, sender)

    response = client.get("/api/v1/admin/signups", headers=user["headers"])

    assert response.status_code == 404


@pytest.mark.parametrize("weeks", [0, 53])
def test_weeks_out_of_range_are_refused(client, db, clock, weeks):
    response = client.get(
        "/api/v1/admin/signups", params={"weeks": weeks}, headers=admin_headers(db, clock)
    )

    assert response.status_code == 422


# --- the export and the database -------------------------------------------------------------


def test_the_export_says_how_i_joined_but_not_whose_code(client, sender):
    inviter_code = code_of(client, sign_up(client, sender))
    user = sign_up(client, sender, arrival={"invite_code": inviter_code})
    my_code = code_of(client, user)

    export = client.get("/api/v1/me/export", headers=user["headers"]).json()

    joined = export["data"]["how_you_joined"][0]
    assert (joined["source"], joined["joined_with_an_invite"]) == ("invite", True)
    assert export["data"]["your_invite_code"][0]["code"] == my_code
    assert inviter_code not in str(export)


def test_the_database_refuses_a_code_without_an_invitation(db):
    account = create_account(db, "creator")

    db.execute(
        text("INSERT INTO invite_code (account_id, code) VALUES (:a, 'ABCDEFGH')"),
        {"a": account.id},
    )

    with pytest.raises(IntegrityError, match="code_means_invite"):
        db.execute(
            text(
                "INSERT INTO account_attribution (account_id, invite_code_id, source) "
                "SELECT :a, id, 'instagram' FROM invite_code WHERE code = 'ABCDEFGH'"
            ),
            {"a": account.id},
        )


@pytest.mark.parametrize("code", ["ABCDEFG0", "abcdefgh", "ABCDEFG", "ABCDEF1H"])
def test_the_database_refuses_a_code_that_could_be_misread(db, code):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match="code_format"):
        db.execute(
            text("INSERT INTO invite_code (account_id, code) VALUES (:a, :c)"),
            {"a": account.id, "c": code},
        )
        db.flush()


def test_codes_are_random_and_readable():
    codes = {new_code() for _ in range(200)}

    assert len(codes) == 200
    assert all(set(code) <= set(CODE_ALPHABET) for code in codes)
    assert normalise_code(" ab cd-ef gh ") == "ABCDEFGH"


def test_an_old_account_with_no_record_is_not_counted(client, db, clock, sender):
    create_account(db, "creator")  # made before attribution existed: no row
    sign_up(client, sender, arrival={"source": "search"})

    rows = client.get("/api/v1/admin/signups", headers=admin_headers(db, clock)).json()

    assert sum(row["accounts"] for row in rows) == sum(
        1 for _ in db.scalars(select(AccountAttribution.id))
    )
