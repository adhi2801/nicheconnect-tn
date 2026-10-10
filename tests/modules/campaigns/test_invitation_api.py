"""Brands invite creators; creators answer in one tap (D-084).

Every test goes through HTTP, from both sides of a real campaign. The rules
that matter: only the campaign's brand invites, only to an open campaign,
once per creator; only the invited creator answers; each side may make only
its own moves; the other side is always told; and the database itself
refuses an invitation that breaks the rules.
"""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.creator import Creator
from app.modules.campaigns import invitation_service
from app.modules.campaigns.invitation_router import WRITE_LIMIT
from app.modules.campaigns.models import Application
from tests.deal_flow import (
    AGREED_DUE_ON,
    CAMPAIGNS_URL,
    MEMOS_URL,
    NOTIFICATIONS_URL,
    PITCH,
    User,
    brand_user,
    creator_user,
)
from tests.modules.auth.test_suspension_api import suspend
from tests.query_counts import queries_for

APPLICATIONS_URL = "/api/v1/applications"
NOTE = "Loved your Madurai food walks. Our Pongal box would suit them."


def open_campaign(client, brand: User, **fields: object) -> str:
    body: dict[str, object] = {
        "title": "Pongal sweets launch",
        "description": "Three reels featuring our new sweet box.",
        "campaign_type": "paid",
        "budget_min_paise": 500_000,
        "budget_max_paise": 1_500_000,
        "cities": ["Madurai"],
        "niches": ["food"],
        "deliverables": "3 Instagram reels",
    }
    body.update(fields)
    campaign_id = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers).json()[
        "id"
    ]
    published = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers
    )
    assert published.status_code == 200, published.text
    return str(campaign_id)


def creator_id_of(db, user: User) -> str:
    return str(db.scalar(select(Creator.id).where(Creator.account_id == user.account_id)))


def invite(client, brand: User, campaign_id: str, creator_id: str, **body: object):
    return client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/invitations",
        json={"creator_id": creator_id, **body},
        headers=brand.headers,
    )


def answer(client, user: User, invitation_id: str, action: str, **body: object):
    return client.post(
        f"{APPLICATIONS_URL}/{invitation_id}/{action}",
        json=body or None,
        headers=user.headers,
    )


def notifications_of(client, user: User) -> list[dict]:
    return client.get(NOTIFICATIONS_URL, headers=user.headers).json()["items"]


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def campaign_id(client, brand) -> str:
    return open_campaign(client, brand)


@pytest.fixture
def invitation(client, db, brand, creator, campaign_id) -> str:
    response = invite(client, brand, campaign_id, creator_id_of(db, creator), note=NOTE)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


# --- inviting -----------------------------------------------------------------------------


def test_a_brand_invites_a_creator(client, db, brand, creator, campaign_id):
    response = invite(client, brand, campaign_id, creator_id_of(db, creator), note=NOTE)

    assert response.status_code == 201, response.text
    body = response.json()
    assert response.headers["Location"] == f"/api/v1/applications/{body['id']}"
    assert body["origin"] == "invited"
    assert body["status"] == "invited"
    assert body["pitch"] is None
    assert body["invitation_note"] == NOTE
    assert body["repeat_of_application_id"] is None
    assert body["creator_id"] == creator_id_of(db, creator)


def test_the_creator_is_told_at_once(client, brand, creator, invitation, campaign_id):
    [told] = notifications_of(client, creator)

    assert told["notification_type"] == "invitation_received"
    assert told["application_id"] == invitation
    assert told["campaign_id"] == campaign_id
    assert told["details"]["campaign_title"] == "Pongal sweets launch"
    assert told["details"]["repeat"] is False
    assert told["details"]["brand_name"]


def test_the_creator_finds_it_in_their_list_and_their_to_do(client, creator, invitation):
    listed = client.get(
        f"{APPLICATIONS_URL}/me", params={"status": "invited"}, headers=creator.headers
    ).json()["items"]
    attention = client.get("/api/v1/me/attention", headers=creator.headers).json()

    assert [row["id"] for row in listed] == [invitation]
    assert [item["application_id"] for item in attention["items"]] == [invitation]
    assert attention["items"][0]["kind"] == "answer_invitation"
    assert attention["counts"]["answer_invitation"] == 1


def test_the_brand_sees_it_among_the_campaigns_applications(
    client, brand, campaign_id, invitation
):
    listed = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", headers=brand.headers
    ).json()["items"]

    assert [(row["id"], row["origin"]) for row in listed] == [(invitation, "invited")]


def test_a_note_is_optional(client, db, brand, creator, campaign_id):
    response = invite(client, brand, campaign_id, creator_id_of(db, creator))

    assert response.status_code == 201
    assert response.json()["invitation_note"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"note": "   "},
        {"note": "x" * 501},
        {"note": NOTE, "pitch": PITCH},
    ],
    ids=["blank note", "note too long", "unknown field"],
)
def test_a_bad_invitation_is_refused(client, db, brand, creator, campaign_id, body):
    response = invite(client, brand, campaign_id, creator_id_of(db, creator), **body)

    assert response.status_code == 422


def test_only_to_an_open_campaign(client, db, brand, creator):
    draft = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Diwali",
            "description": "Lights.",
            "campaign_type": "barter",
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "1 reel",
        },
        headers=brand.headers,
    ).json()["id"]

    response = invite(client, brand, draft, creator_id_of(db, creator))

    assert_problem(response, 409, "campaign_not_open")


def test_not_to_another_brands_campaign(client, db, clock, creator, campaign_id):
    stranger = brand_user(db, clock)

    response = invite(client, stranger, campaign_id, creator_id_of(db, creator))

    assert_problem(response, 404, "campaign_not_found")


def test_an_unknown_creator_is_not_found(client, brand, campaign_id):
    response = invite(client, brand, campaign_id, str(uuid.uuid4()))

    assert_problem(response, 404, "creator_not_found")


def test_a_suspended_creator_cannot_be_invited(client, db, brand, creator, campaign_id):
    suspend(db, creator.account_id)

    response = invite(client, brand, campaign_id, creator_id_of(db, creator))

    assert_problem(response, 404, "creator_not_found")


def test_a_creator_is_invited_once(client, db, brand, creator, campaign_id, invitation):
    response = invite(client, brand, campaign_id, creator_id_of(db, creator))

    assert_problem(response, 409, "creator_already_on_campaign")


def test_a_creator_who_applied_is_not_invited_too(
    client, db, brand, creator, campaign_id
):
    client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    response = invite(client, brand, campaign_id, creator_id_of(db, creator))

    assert_problem(response, 409, "creator_already_on_campaign")


def test_an_invited_creator_is_pointed_to_the_invitation(
    client, creator, campaign_id, invitation
):
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    assert_problem(response, 409, "invitation_pending")


def test_a_campaign_has_a_limit_on_unanswered_invitations(
    client, db, clock, brand, campaign_id, monkeypatch
):
    monkeypatch.setattr(invitation_service, "MAX_WAITING_INVITATIONS", 2)
    invited = []
    for _ in range(2):
        response = invite(
            client, brand, campaign_id, creator_id_of(db, creator_user(db, clock))
        )
        assert response.status_code == 201
        invited.append(response.json()["id"])

    third = creator_id_of(db, creator_user(db, clock))
    assert_problem(
        invite(client, brand, campaign_id, third), 409, "invitation_limit_reached"
    )

    # Taking one back makes room; an answered one would too. (A fresh
    # creator: the refusal rolled back the test's uncommitted one.)
    answer(client, brand, invited[0], "withdraw-invitation")
    fourth = creator_id_of(db, creator_user(db, clock))
    assert invite(client, brand, campaign_id, fourth).status_code == 201


def test_the_limit_is_twenty_five():
    assert invitation_service.MAX_WAITING_INVITATIONS == 25


def test_a_creator_cannot_invite(client, db, creator, campaign_id):
    response = invite(client, creator, campaign_id, creator_id_of(db, creator))

    assert response.status_code == 403


def test_without_a_token_it_is_refused(client, campaign_id):
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/invitations",
        json={"creator_id": str(uuid.uuid4())},
    )

    assert response.status_code == 401


def test_a_retry_with_the_same_key_invites_once(client, db, brand, creator, campaign_id):
    headers = {**brand.headers, "Idempotency-Key": str(uuid.uuid4())}
    body = {"creator_id": creator_id_of(db, creator)}
    url = f"{CAMPAIGNS_URL}/{campaign_id}/invitations"

    first = client.post(url, json=body, headers=headers)
    second = client.post(url, json=body, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_inviting_is_rate_limited(client, db, clock, brand, campaign_id, monkeypatch):
    monkeypatch.setattr(invitation_service, "MAX_WAITING_INVITATIONS", 1000)
    allowed = int(WRITE_LIMIT.split()[0])
    creators = [creator_id_of(db, creator_user(db, clock)) for _ in range(allowed + 1)]

    answers = [invite(client, brand, campaign_id, c).status_code for c in creators]

    assert answers[:allowed] == [201] * allowed
    assert answers[allowed] == 429


# --- answering --------------------------------------------------------------------------


def test_accepting_makes_it_accepted_and_tells_the_brand(
    client, brand, creator, invitation
):
    response = answer(client, creator, invitation, "accept-invitation")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    told = [
        n for n in notifications_of(client, brand) if n["application_id"] == invitation
    ]
    assert [n["notification_type"] for n in told] == ["invitation_accepted"]


def test_an_accepted_invitation_leads_to_the_memo(client, brand, creator, invitation):
    answer(client, creator, invitation, "accept-invitation")

    [item] = [
        i
        for i in client.get("/api/v1/me/attention", headers=brand.headers).json()["items"]
        if i["kind"] == "draft_memo"
    ]
    memo = client.post(
        f"{MEMOS_URL}/for-application/{invitation}",
        json={
            "deliverables": "2 reels",
            "fee_amount_paise": 600_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    )

    assert item["application_id"] == invitation
    assert item["memo_id"] is None
    assert memo.status_code == 201, memo.text


def test_declining_says_why_and_tells_the_brand(client, brand, creator, invitation):
    response = answer(client, creator, invitation, "decline-invitation", reason="timing")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "declined"
    assert response.json()["decline_reason"] == "timing"
    [told] = [
        n for n in notifications_of(client, brand) if n["application_id"] == invitation
    ]
    assert told["notification_type"] == "invitation_declined"
    assert told["details"]["reason"] == "timing"


@pytest.mark.parametrize("body", [{}, {"reason": "bored"}], ids=["no reason", "unknown"])
def test_a_decline_needs_a_known_reason(client, creator, invitation, body):
    response = answer(client, creator, invitation, "decline-invitation", **body)

    assert response.status_code == 422


def test_the_brand_may_take_it_back_and_the_creator_is_told(
    client, brand, creator, invitation
):
    response = answer(client, brand, invitation, "withdraw-invitation")

    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"
    assert "invitation_withdrawn" in [
        n["notification_type"] for n in notifications_of(client, creator)
    ]
    assert_problem(
        answer(client, creator, invitation, "accept-invitation"),
        409,
        "application_status_conflict",
    )


@pytest.mark.parametrize("first", ["accept-invitation", "decline-invitation"])
def test_an_answer_is_final(client, creator, invitation, first):
    answer(
        client,
        creator,
        invitation,
        first,
        **({"reason": "budget"} if "decline" in first else {}),
    )

    again = answer(client, creator, invitation, "accept-invitation")

    assert_problem(again, 409, "application_status_conflict")


def test_after_the_campaign_closes_it_cannot_be_accepted(
    client, brand, creator, campaign_id, invitation
):
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/close", headers=brand.headers)

    response = answer(client, creator, invitation, "accept-invitation")

    assert_problem(response, 409, "campaign_not_open")


def test_a_suspended_brands_invitation_cannot_be_accepted(
    client, db, brand, creator, invitation
):
    suspend(db, brand.account_id)

    response = answer(client, creator, invitation, "accept-invitation")

    assert_problem(response, 409, "campaign_not_open")


# --- each side makes only its own moves ---------------------------------------------------


@pytest.mark.parametrize("action", ["shortlist", "accept"])
def test_the_brand_cannot_decide_an_invitation_as_if_it_were_an_application(
    client, brand, invitation, action
):
    response = answer(client, brand, invitation, action)

    assert_problem(response, 409, "application_status_conflict")


def test_the_brand_cannot_reject_an_invitation(client, brand, invitation):
    response = answer(client, brand, invitation, "reject", reason="timing")

    assert_problem(response, 409, "application_status_conflict")


def test_the_creator_declines_rather_than_withdrawing_it(client, creator, invitation):
    response = answer(client, creator, invitation, "withdraw")

    assert_problem(response, 409, "application_status_conflict")


def test_an_application_cannot_be_answered_as_an_invitation(
    client, brand, creator, campaign_id
):
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]

    assert_problem(
        answer(client, creator, application_id, "accept-invitation"),
        409,
        "application_status_conflict",
    )
    assert_problem(
        answer(client, brand, application_id, "withdraw-invitation"),
        409,
        "application_status_conflict",
    )


def test_another_creator_cannot_answer_it(client, db, clock, invitation):
    stranger = creator_user(db, clock)

    response = answer(client, stranger, invitation, "accept-invitation")

    assert_problem(response, 404, "application_not_found")


def test_another_brand_cannot_take_it_back(client, db, clock, invitation):
    stranger = brand_user(db, clock)

    response = answer(client, stranger, invitation, "withdraw-invitation")

    assert_problem(response, 404, "application_not_found")


@pytest.mark.parametrize(
    "action", ["accept-invitation", "decline-invitation", "withdraw-invitation"]
)
def test_answering_needs_a_login(client, invitation, action):
    response = client.post(
        f"{APPLICATIONS_URL}/{invitation}/{action}", json={"reason": "timing"}
    )

    assert response.status_code == 401


def test_answering_is_rate_limited(client, creator, invitation):
    allowed = int(WRITE_LIMIT.split()[0])

    answers = [
        answer(client, creator, invitation, "accept-invitation").status_code
        for _ in range(allowed + 1)
    ]

    assert answers[0] == 200
    assert answers[allowed] == 429


# --- what it counts for -------------------------------------------------------------------


def test_the_campaign_summary_counts_invitations(
    client, db, clock, brand, creator, campaign_id, invitation
):
    other = invite(client, brand, campaign_id, creator_id_of(db, creator_user(db, clock)))
    answer(client, creator, invitation, "decline-invitation", reason="budget")

    summary = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/summary", headers=brand.headers
    ).json()

    assert other.status_code == 201
    assert summary["applications"]["invited"] == 1
    assert summary["applications"]["declined"] == 1


def test_an_invitation_is_not_counted_as_the_creators_own_application(
    client, creator, invitation
):
    answer(client, creator, invitation, "decline-invitation", reason="budget")

    feedback = client.get(
        f"{APPLICATIONS_URL}/me/feedback", headers=creator.headers
    ).json()

    assert feedback["applications"] == 0
    assert feedback["by_status"]["declined"] == 0


def test_both_sides_export_it(client, brand, creator, invitation):
    answer(client, creator, invitation, "decline-invitation", reason="not_a_fit")

    brand_rows = client.get("/api/v1/me/export", headers=brand.headers).json()["data"][
        "applications_received"
    ]
    creator_rows = client.get("/api/v1/me/export", headers=creator.headers).json()[
        "data"
    ]["applications_sent"]

    for rows in (brand_rows, creator_rows):
        [row] = rows
        assert row["origin"] == "invited"
        assert row["invitation_note"] == NOTE
        assert row["decline_reason"] == "not_a_fit"


def test_a_mixed_list_costs_no_more_queries(client, db, clock, brand, campaign_id):
    url = f"{CAMPAIGNS_URL}/{campaign_id}/applications"
    invite(client, brand, campaign_id, creator_id_of(db, creator_user(db, clock)))
    one = queries_for(client, url, brand.headers)

    for _ in range(4):
        invite(client, brand, campaign_id, creator_id_of(db, creator_user(db, clock)))
    five = queries_for(client, url, brand.headers)

    assert five == one


def test_the_creators_to_do_costs_no_more_queries_with_more_invitations(
    client, db, clock, creator
):
    url = "/api/v1/me/attention"
    creator_id = creator_id_of(db, creator)
    first = brand_user(db, clock)
    invite(client, first, open_campaign(client, first), creator_id)
    one = queries_for(client, url, creator.headers)

    for _ in range(3):
        other = brand_user(db, clock)
        invite(client, other, open_campaign(client, other), creator_id)
    four = queries_for(client, url, creator.headers)

    assert four == one


# --- the database's own rules ---------------------------------------------------------------


def _insert(db, campaign_id: str, creator_id: str, columns: dict[str, object]) -> None:
    names = ", ".join(columns)
    values = ", ".join(f":{name}" for name in columns)
    db.execute(
        text(
            # Column names from this file's own cases; every value is bound.
            f"INSERT INTO application (campaign_id, creator_id, {names}) "  # noqa: S608
            f"VALUES (:campaign_id, :creator_id, {values})"
        ),
        {"campaign_id": campaign_id, "creator_id": creator_id, **columns},
    )


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        (
            {"origin": "invited", "pitch": PITCH, "status": "invited"},
            "pitch_matches_origin",
        ),
        ({"origin": "applied", "status": "submitted"}, "pitch_matches_origin"),
        (
            {"origin": "applied", "pitch": PITCH, "status": "invited"},
            "invitation_fields_need_invitation",
        ),
        (
            {
                "origin": "applied",
                "pitch": PITCH,
                "status": "submitted",
                "invitation_note": NOTE,
            },
            "invitation_fields_need_invitation",
        ),
        ({"origin": "invited", "status": "shortlisted"}, "invitation_status_allowed"),
        ({"origin": "invited", "status": "declined"}, "decline_reason_matches_status"),
        (
            {"origin": "invited", "status": "invited", "decline_reason": "timing"},
            "decline_reason_matches_status",
        ),
        (
            {"origin": "invited", "status": "declined", "decline_reason": "bored"},
            "decline_reason_allowed",
        ),
        (
            {"origin": "invited", "status": "invited", "invitation_note": ""},
            "invitation_note_length",
        ),
        (
            {"origin": "elsewhere", "status": "accepted"},
            "origin_allowed",
        ),
        ({"origin": "applied", "pitch": PITCH, "status": "maybe"}, "status_allowed"),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_the_database_refuses_a_broken_invitation(
    db, brand, creator, campaign_id, columns, constraint
):
    with pytest.raises(IntegrityError, match=f"ck_application_{constraint}"):
        _insert(db, campaign_id, creator_id_of(db, creator), columns)


def test_the_database_refuses_a_repeat_that_names_itself(db, creator, campaign_id):
    row_id = uuid.uuid4()

    with pytest.raises(IntegrityError, match="ck_application_repeat_not_itself"):
        db.execute(
            text(
                "INSERT INTO application (id, campaign_id, creator_id, origin, status,"
                " repeat_of_application_id) VALUES (:id, :campaign_id, :creator_id,"
                " 'invited', 'invited', :id)"
            ),
            {
                "id": row_id,
                "campaign_id": campaign_id,
                "creator_id": creator_id_of(db, creator),
            },
        )


def test_an_invitation_row_needs_no_pitch(db, creator, campaign_id):
    _insert(
        db,
        campaign_id,
        creator_id_of(db, creator),
        {"origin": "invited", "status": "invited"},
    )

    row = db.scalars(
        select(Application).where(Application.campaign_id == campaign_id)
    ).one()
    assert (row.origin, row.pitch) == ("invited", None)
