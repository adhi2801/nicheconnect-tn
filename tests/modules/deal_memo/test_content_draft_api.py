"""Drafts shown before posting (item 27, D-140), through the API.

A memo agreed with `draft_review` seals it with its terms (version 3); the
creator shows a draft, the brand approves it or asks for changes within the
approval window, silence approves by the clock (D-025), and proof waits for
an approved draft and names it on the record. The table's own rules are in
test_content_draft_model.py, races in test_content_draft_concurrency.py.
"""

import hashlib
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auth.models.account import Account
from app.modules.deal_memo import record_service
from app.modules.deal_memo.models import DealMemo
from app.modules.me import export_service
from app.modules.notifications.models import Notification
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)

BODY = "Pongal at home, the Madurai way. Our new sweet box serves six. #ad"
PROOF = {"content_url": LINK, "format": "reel", "disclosure_confirmed": True}


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def memo_id(client, brand, creator) -> str:
    """An accepted deal whose terms include a draft review."""
    return accepted_memo(client, brand, creator, draft_review=True)


def drafts_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/drafts"


def show(client, creator: User, memo_id: str, body: str = BODY, **fields):
    return client.post(
        drafts_url(memo_id), json={"body": body, **fields}, headers=creator.headers
    )


def shown(client, creator: User, memo_id: str, **fields) -> dict:
    response = show(client, creator, memo_id, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, brand: User, memo_id: str, draft_id: str):
    return client.post(f"{drafts_url(memo_id)}/{draft_id}/approve", headers=brand.headers)


def ask_changes(
    client, brand: User, memo_id: str, draft_id: str, note: str = "Add the ad label."
):
    return client.post(
        f"{drafts_url(memo_id)}/{draft_id}/request-changes",
        json={"note": note},
        headers=brand.headers,
    )


def entries(client, user: User, memo_id: str) -> list[dict]:
    response = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def memo_read(client, user: User, memo_id: str) -> dict:
    return client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers).json()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def told(db, user: User, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


# --- the term, sealed ---------------------------------------------------------------


def test_the_term_is_sealed_with_the_terms_as_version_three(client, db, brand, memo_id):
    memo = db.get_one(DealMemo, memo_id)
    assert memo.terms_version == 3
    assert memo_read(client, brand, memo_id)["draft_review"] is True
    terms = {field: getattr(memo, field) for field in record_service.TERMS_FIELDS}
    terms["content_due_on"] = memo.content_due_on.isoformat()
    terms["deliverable_items"] = [
        {f: getattr(item, f) for f in record_service.DELIVERABLE_FIELDS}
        for item in memo.deliverable_items
    ]
    terms["draft_review"] = True

    expected = hashlib.sha256(record_service.canonical(terms)).hexdigest()

    assert record_service.terms_fingerprint(memo) == expected
    memo.draft_review = False
    assert record_service.terms_fingerprint(memo) != expected


def test_an_older_version_never_seals_the_term(db, memo_id):
    """A version 2 seal stays exactly what it was, whatever draft_review says."""
    memo = db.get_one(DealMemo, memo_id)
    memo.terms_version = 2
    sealed = record_service.terms_fingerprint(memo)

    memo.draft_review = False

    assert record_service.terms_fingerprint(memo) == sealed


def test_a_deal_without_the_term_takes_no_draft(client, brand, creator):
    plain = accepted_memo(client, brand, creator)

    assert_problem(show(client, creator, plain), 409, "draft_review_not_agreed")


def test_a_memo_not_yet_accepted_takes_no_draft(client, db, brand, creator, memo_id):
    memo = db.get_one(DealMemo, memo_id)
    memo.status = "sent"
    db.flush()

    assert_problem(show(client, creator, memo_id), 409, "memo_status_conflict")


# --- showing, answering ---------------------------------------------------------------


def test_the_creator_shows_a_draft_and_the_brand_is_told(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id, note="Two options for the hook.")

    assert (draft["round"], draft["status"], draft["auto_approved"]) == (
        1,
        "submitted",
        False,
    )
    # Shown today, a 7-day window: the brand decides by the 7th day after.
    assert draft["answer_by"] == (clock.now.date() + timedelta(days=7)).isoformat()
    assert len(told(db, brand, "draft_submitted")) == 1
    [entry] = [
        e for e in entries(client, brand, memo_id) if e["kind"] == "draft_submitted"
    ]
    assert entry["facts"]["body_sha256"] == hashlib.sha256(BODY.encode()).hexdigest()
    assert BODY not in str(entry)
    assert db.get_one(DealMemo, memo_id).work_started_at is not None


def test_one_draft_waits_at_a_time(client, creator, memo_id):
    shown(client, creator, memo_id)

    assert_problem(show(client, creator, memo_id), 409, "draft_already_decided")


def test_the_brand_approves_and_the_creator_is_told(client, db, brand, creator, memo_id):
    draft = shown(client, creator, memo_id)

    approved = approve(client, brand, memo_id, draft["id"])

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["answer_by"] is None
    assert len(told(db, creator, "draft_approved")) == 1
    assert_problem(
        approve(client, brand, memo_id, draft["id"]), 409, "draft_already_decided"
    )
    assert_problem(show(client, creator, memo_id), 409, "draft_already_decided")


def test_changes_asked_and_a_second_round(client, db, brand, creator, memo_id):
    first = shown(client, creator, memo_id)

    asked = ask_changes(
        client, brand, memo_id, first["id"], "Pay a 2,000 registration fee to confirm."
    )

    assert asked.status_code == 200, asked.text
    assert asked.json()["status"] == "changes_requested"
    assert asked.json()["changes_note"] == "Pay a 2,000 registration fee to confirm."
    # A brand's note asking the creator for money is flagged (item 60).
    assert any(flag["field"] == "changes_note" for flag in asked.json()["text_flags"])
    assert len(told(db, creator, "draft_changes_requested")) == 1
    second = shown(client, creator, memo_id, body=BODY + " Now with the ad label.")
    assert second["round"] == 2
    listed = client.get(drafts_url(memo_id), headers=brand.headers).json()
    assert [d["round"] for d in listed] == [2, 1]


def test_only_the_brand_answers_and_only_the_creator_shows(
    client, brand, creator, memo_id
):
    draft = shown(client, creator, memo_id)

    assert approve(client, creator, memo_id, draft["id"]).status_code == 403
    assert show(client, brand, memo_id).status_code == 403


def test_another_brand_never_reaches_the_draft(client, db, clock, creator, memo_id):
    draft = shown(client, creator, memo_id)
    stranger = brand_user(db, clock)

    assert approve(client, stranger, memo_id, draft["id"]).status_code == 404
    assert client.get(drafts_url(memo_id), headers=stranger.headers).status_code == 404


def test_a_draft_of_another_deal_is_not_found(client, db, clock, brand, creator, memo_id):
    other_creator = creator_user(db, clock)
    other = accepted_memo(client, brand, other_creator, draft_review=True)
    foreign = shown(client, other_creator, other)

    assert_problem(approve(client, brand, memo_id, foreign["id"]), 404, "draft_not_found")


@pytest.mark.parametrize(
    "fields",
    [
        {"body": ""},
        {"body": "x" * 5001},
        {"content_url": "http://example.com/draft"},
        {"note": "x" * 1001},
        {"extra": "field"},
    ],
)
def test_a_draft_outside_the_limits_is_refused(client, creator, memo_id, fields):
    response = client.post(
        drafts_url(memo_id), json={"body": BODY, **fields}, headers=creator.headers
    )

    assert response.status_code == 422, response.text


def test_a_changes_note_too_short_is_refused(client, brand, creator, memo_id):
    draft = shown(client, creator, memo_id)

    assert ask_changes(client, brand, memo_id, draft["id"], "No").status_code == 422


# --- the clock ------------------------------------------------------------------------


def test_silence_approves_by_the_clock(client, db, brand, creator, memo_id, clock):
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(days=8))

    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()

    assert (listed["status"], listed["auto_approved"]) == ("approved", True)
    assert len(told(db, creator, "draft_auto_approved")) == 1
    [entry] = [
        e for e in entries(client, brand, memo_id) if e["kind"] == "draft_auto_approved"
    ]
    assert entry["actor_role"] == "system"
    assert_problem(
        approve(client, brand, memo_id, draft["id"]), 409, "draft_already_decided"
    )


def test_a_day_before_the_deadline_the_brand_still_decides(
    client, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(days=7))

    assert approve(client, brand, memo_id, draft["id"]).status_code == 200


def test_only_the_first_request_restarts_the_clock(
    client, brand, creator, memo_id, clock
):
    """D-025's rule for proof holds for drafts: asking again buys no more time."""
    first = shown(client, creator, memo_id)
    ask_changes(client, brand, memo_id, first["id"])
    clock.advance(timedelta(days=3))
    second = shown(client, creator, memo_id)
    ask_changes(client, brand, memo_id, second["id"])
    clock.advance(timedelta(days=3))

    third = shown(client, creator, memo_id)

    # Runs on the second draft's clock, restarted three days ago.
    assert third["answer_by"] == (clock.now.date() + timedelta(days=4)).isoformat()


# --- proof waits for an approved draft --------------------------------------------------


def test_proof_waits_for_an_approved_draft(client, brand, creator, memo_id):
    url = f"{MEMOS_URL}/{memo_id}/proof"

    assert_problem(
        client.post(url, json=PROOF, headers=creator.headers), 409, "draft_not_approved"
    )
    draft = shown(client, creator, memo_id)
    assert_problem(
        client.post(url, json=PROOF, headers=creator.headers), 409, "draft_not_approved"
    )
    approve(client, brand, memo_id, draft["id"])

    proof = client.post(url, json=PROOF, headers=creator.headers)

    assert proof.status_code == 201, proof.text
    [entry] = [
        e for e in entries(client, brand, memo_id) if e["kind"] == "proof_submitted"
    ]
    assert entry["facts"]["draft_id"] == draft["id"]
    assert (
        entry["facts"]["draft_body_sha256"] == hashlib.sha256(BODY.encode()).hexdigest()
    )


def test_a_draft_approved_by_the_clock_lets_proof_through_unread(
    client, creator, memo_id, clock
):
    """The proof check reads the clock itself; nobody has to open the drafts first."""
    shown(client, creator, memo_id)
    clock.advance(timedelta(days=8))

    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
    )

    assert proof.status_code == 201, proof.text


def test_a_deal_without_the_term_takes_proof_as_before(client, brand, creator):
    plain = accepted_memo(client, brand, creator)

    proof = client.post(f"{MEMOS_URL}/{plain}/proof", json=PROOF, headers=creator.headers)

    assert proof.status_code == 201, proof.text
    [entry] = [e for e in entries(client, brand, plain) if e["kind"] == "proof_submitted"]
    assert "draft_id" not in entry["facts"]


# --- where the deal stands, and what needs whom -------------------------------------------


def test_the_stage_follows_the_draft(client, brand, creator, memo_id):
    def stage(user):
        found = memo_read(client, user, memo_id)
        return found["stage"], found["waiting_on"]

    assert stage(brand) == ("agreed", "creator")
    draft = shown(client, creator, memo_id)
    assert stage(brand) == ("draft_review", "brand")
    ask_changes(client, brand, memo_id, draft["id"])
    assert stage(creator) == ("draft_review", "creator")
    approve(client, brand, memo_id, shown(client, creator, memo_id)["id"])
    # Approved: the work goes ahead, and a draft shown counts as work started.
    assert stage(creator) == ("in_progress", "creator")


def test_the_campaign_summary_counts_draft_review(client, brand, creator, memo_id):
    shown(client, creator, memo_id)
    [campaign] = client.get("/api/v1/campaigns", headers=brand.headers).json()["items"]

    summary = client.get(
        f"/api/v1/campaigns/{campaign['id']}/summary", headers=brand.headers
    )

    assert summary.status_code == 200, summary.text
    assert summary.json()["deals_by_stage"]["draft_review"] == 1


def test_attention_names_whose_move_it_is(client, brand, creator, memo_id):
    def kinds(user):
        found = client.get("/api/v1/me/attention", headers=user.headers).json()["items"]
        return {item["kind"]: item for item in found}

    assert "show_draft" in kinds(creator)
    draft = shown(client, creator, memo_id)
    waiting = kinds(brand)["review_draft"]
    assert waiting["draft_id"] == draft["id"]
    assert "show_draft" not in kinds(creator)
    ask_changes(client, brand, memo_id, draft["id"])
    assert "revise_draft" in kinds(creator)
    assert "review_draft" not in kinds(brand)


def test_the_brand_need_not_review_a_draft_past_its_window(
    client, brand, creator, memo_id, clock
):
    shown(client, creator, memo_id)
    clock.advance(timedelta(days=8))

    found = client.get("/api/v1/me/attention", headers=brand.headers).json()["items"]

    assert "review_draft" not in {item["kind"] for item in found}


# --- a repeat, the export ---------------------------------------------------------------


def test_both_sides_export_the_drafts(client, db, brand, creator, memo_id, clock):
    draft = shown(client, creator, memo_id)

    for user in (brand, creator):
        account = db.get_one(Account, user.account_id)
        [section] = [
            s
            for s in export_service.collect_sections(db, account, clock.now)
            if s.table == "content_draft"
        ]
        assert [record["id"] for record in section.records] == [draft["id"]]
        assert section.records[0]["body"] == BODY
