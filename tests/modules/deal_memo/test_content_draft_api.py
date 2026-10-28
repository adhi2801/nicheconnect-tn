"""Drafts shown before posting (item 27, D-140), through the API.

A memo agreed with `draft_review` seals it with its terms (version 3); the
creator shows a draft, the brand approves it or asks for changes within the
approval window, silence approves by the clock (D-025), and proof waits for
an approved draft and names it on the record. The table's own rules are in
test_content_draft_model.py, races in test_content_draft_concurrency.py.
"""

import hashlib
from csv import DictReader
from datetime import UTC, date, datetime, timedelta
from io import StringIO

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


# --- found by the independent review (27 October 2026) ---------------------------------


def creator_id_of(db, user: User) -> str:
    from app.modules.auth.models.creator import Creator

    return str(
        db.scalars(select(Creator.id).where(Creator.account_id == user.account_id)).one()
    )


def test_the_brands_waiting_moves_the_creators_due_date(
    client, db, brand, creator, clock
):
    """Adhi's choice: every day a draft waits for the brand is added to the due date."""
    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-20"
    )
    shown(client, creator, memo_id)
    clock.advance(
        timedelta(days=6)
    )  # the agreed date is 3 days past; the brand is silent

    record = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/delivery-record",
        headers=brand.headers,
    ).json()

    assert record["currently_overdue"] == 0


def test_once_answered_the_moved_date_holds(client, db, brand, creator, clock):
    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-20"
    )
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(days=5))
    approve(client, brand, memo_id, draft["id"])
    clock.advance(timedelta(days=4))  # due 20 Sep + 5 days waited = 25 Sep; now 26 Sep

    record = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/delivery-record",
        headers=brand.headers,
    ).json()

    assert record["currently_overdue"] == 1


def test_every_draft_gets_two_whole_days(client, brand, creator, memo_id, clock):
    """Adhi's choice: a draft shown long after the clock restarted is not approved at once."""
    first = shown(client, creator, memo_id)
    ask_changes(client, brand, memo_id, first["id"])
    second = shown(client, creator, memo_id)
    ask_changes(client, brand, memo_id, second["id"])
    clock.advance(timedelta(days=20))  # far past round 2's clock

    third = shown(client, creator, memo_id)

    assert third["status"] == "submitted"
    assert third["answer_by"] == (clock.now.date() + timedelta(days=2)).isoformat()
    assert approve(client, brand, memo_id, third["id"]).status_code == 200


def test_a_deal_in_draft_review_is_agreed_and_keeps_a_campaign_open(
    client, db, brand, creator, memo_id
):
    shown(client, creator, memo_id)
    [campaign] = client.get("/api/v1/campaigns", headers=brand.headers).json()["items"]

    summary = client.get(
        f"/api/v1/campaigns/{campaign['id']}/summary", headers=brand.headers
    ).json()

    assert summary["deals_agreed"] == 1
    assert summary["complete"] is False


def test_a_memo_made_before_version_three_cannot_take_the_term(
    client, db, brand, creator
):
    from tests.modules.deal_memo.test_memo_deliverables_api import (
        accepted_application,
        draft,
    )

    memo = draft(client, brand, accepted_application(client, brand, creator))
    db.get_one(DealMemo, memo["id"]).terms_version = 2
    db.flush()

    response = client.patch(
        f"{MEMOS_URL}/{memo['id']}", json={"draft_review": True}, headers=brand.headers
    )

    assert_problem(response, 409, "draft_review_needs_new_terms")


@pytest.mark.parametrize(
    "field",
    [
        "deliverables",
        "deliverable_items",
        "cancellation_fee_paise",
        "approval_window_days",
        "payment_due_days",
        "disclosure_required",
        "draft_review",
    ],
)
def test_a_term_that_always_has_a_value_cannot_be_emptied(client, brand, creator, field):
    from tests.modules.deal_memo.test_memo_deliverables_api import (
        accepted_application,
        draft,
    )

    memo = draft(client, brand, accepted_application(client, brand, creator))

    response = client.patch(
        f"{MEMOS_URL}/{memo['id']}", json={field: None}, headers=brand.headers
    )

    assert response.status_code == 422, response.text


def test_a_cancelled_deals_draft_is_never_answered(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    memo = db.get_one(DealMemo, memo_id)
    memo.status = "cancelled"
    memo.cancellation_kind = "cancelled_by_brand"
    # Committed, so the app's rollback on refusing cannot undo it.
    db.commit()
    clock.advance(timedelta(days=8))

    assert_problem(
        approve(client, brand, memo_id, draft["id"]), 409, "memo_status_conflict"
    )
    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()
    assert listed["status"] == "submitted"  # never approved by the clock
    assert told(db, creator, "draft_auto_approved") == []


def test_an_answer_that_read_its_clock_before_the_proof_is_refused(
    client, db, brand, creator, memo_id, clock
):
    """The brand asked at 23:59:59 and waited for the lock behind a proof at 00:00:01.

    Its moment is before the deadline, so the clock alone would let it
    through; the proof already following the draft is what refuses it.
    """
    from app.modules.deal_memo import draft_service
    from app.modules.deal_memo.draft_models import ContentDraft
    from app.modules.deal_memo.draft_rules import answer_deadline
    from app.modules.deal_memo.exceptions import DraftAlreadyDecided

    draft = shown(client, creator, memo_id)
    row = db.get_one(ContentDraft, draft["id"])
    deadline = answer_deadline(db.get_one(DealMemo, memo_id), row, [row])
    clock.now = deadline + timedelta(seconds=1)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
    )
    assert proof.status_code == 201, proof.text

    with pytest.raises(DraftAlreadyDecided):
        draft_service.request_changes(
            db,
            db.get_one(DealMemo, memo_id),
            db.get_one(ContentDraft, draft["id"]),
            "Add the ad label.",
            deadline - timedelta(seconds=1),
        )


def test_work_delivered_inside_the_moved_date_is_on_time(
    client, db, brand, creator, clock
):
    """The campaign report and the creator's record judge on-time the same way."""
    from app.modules.deal_memo.delivery_record import _on_time
    from app.modules.deal_memo.draft_service import drafts_of
    from app.modules.deal_memo.proof_models import DeliverableProof

    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-20"
    )
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(days=6))  # the brand answers on 23 Sep: due moves to 26 Sep
    approve(client, brand, memo_id, draft["id"])
    clock.advance(timedelta(days=1))  # the work goes in on 24 Sep, after the agreed date
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
    )
    assert proof.status_code == 201, proof.text

    [campaign] = client.get("/api/v1/campaigns", headers=brand.headers).json()["items"]
    report = client.get(
        f"/api/v1/campaigns/{campaign['id']}/report", headers=brand.headers
    )

    assert report.json()["deals"][0]["delivered_on_time"] is True
    memo = db.get_one(DealMemo, memo_id)
    proofs = list(
        db.scalars(
            select(DeliverableProof).where(DeliverableProof.deal_memo_id == memo.id)
        )
    )
    assert _on_time(memo, proofs, drafts_of(db, memo)) is True
    assert _on_time(memo, proofs) is False  # judged on the agreed date alone, it was late


# --- the second independent review (27 October 2026) -----------------------------------


def deadline_of(db, memo_id: str, draft_id: str):
    from app.modules.deal_memo.draft_models import ContentDraft
    from app.modules.deal_memo.draft_rules import answer_deadline
    from app.modules.deal_memo.draft_service import drafts_of

    memo = db.get_one(DealMemo, memo_id)
    return answer_deadline(memo, db.get_one(ContentDraft, draft_id), drafts_of(db, memo))


def test_a_second_before_the_deadline_the_brand_answers(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    clock.now = deadline_of(db, memo_id, draft["id"]) - timedelta(seconds=1)

    response = approve(client, brand, memo_id, draft["id"])

    assert response.status_code == 200, response.text
    assert response.json()["auto_approved"] is False


def test_at_the_deadline_the_clock_has_answered(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    deadline = deadline_of(db, memo_id, draft["id"])
    clock.now = deadline

    assert_problem(
        ask_changes(client, brand, memo_id, draft["id"]), 409, "draft_already_decided"
    )
    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()
    assert listed["auto_approved"] is True
    assert listed["approved_at"] == listed["answered_at"]
    assert datetime.fromisoformat(listed["answered_at"]) == deadline


def test_the_moved_date_is_the_due_date_everywhere(client, db, brand, creator, clock):
    """Found by the second review: the deal, the creator's list, the calendar and the report."""
    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-25"
    )
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(days=5, hours=1))  # five whole days waiting
    assert approve(client, brand, memo_id, draft["id"]).status_code == 200

    assert memo_read(client, creator, memo_id)["work_due_on"] == "2026-09-30"
    [item] = [
        i
        for i in client.get("/api/v1/me/attention", headers=creator.headers).json()[
            "items"
        ]
        if i["kind"] == "deliver_work"
    ]
    assert item["due_on"] == "2026-09-30"
    ics = client.get(f"{MEMOS_URL}/{memo_id}/calendar.ics", headers=creator.headers).text
    assert "DTSTART;VALUE=DATE:20260930" in ics
    assert "moved 5 days while a draft waited for the brand" in ics.replace("\r\n ", "")
    [campaign] = client.get("/api/v1/campaigns", headers=brand.headers).json()["items"]
    [deal] = client.get(
        f"/api/v1/campaigns/{campaign['id']}/report", headers=brand.headers
    ).json()["deals"]
    assert (deal["content_due_on"], deal["work_due_on"]) == ("2026-09-25", "2026-09-30")
    csv = client.get(
        f"/api/v1/campaigns/{campaign['id']}/report.csv", headers=brand.headers
    ).text
    [row] = list(DictReader(StringIO(csv)))
    assert (row["content_due_on"], row["work_due_on"]) == ("2026-09-25", "2026-09-30")


def test_a_deal_without_the_term_is_due_on_its_agreed_date(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator, content_due_on="2026-09-25")

    assert memo_read(client, creator, memo_id)["work_due_on"] == "2026-09-25"


def test_crossing_midnight_moves_a_day(client, db, brand, creator, clock):
    """Adhi's choice of calendar days: the creator lost the 25th's posting, so the date moves."""
    from app.core.clock import IST

    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-25"
    )
    clock.now = clock.now.astimezone(IST).replace(hour=23, minute=55)
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(minutes=10))
    approve(client, brand, memo_id, draft["id"])

    assert memo_read(client, creator, memo_id)["work_due_on"] == "2026-09-26"


def test_answered_the_same_day_moves_nothing(client, brand, creator, clock):
    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-25"
    )
    draft = shown(client, creator, memo_id)
    clock.advance(timedelta(hours=5))  # 17:30 to 22:30, Tamil Nadu time
    approve(client, brand, memo_id, draft["id"])

    assert memo_read(client, creator, memo_id)["work_due_on"] == "2026-09-25"


def test_a_draft_held_overnight_on_the_due_day_never_makes_the_creator_late(
    client, db, brand, creator, clock
):
    """Found by the third review: under 24-hour days this creator was counted late."""
    from app.core.clock import IST

    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-20"
    )
    clock.now = datetime(2026, 9, 20, 9, 0, tzinfo=IST)
    draft = shown(client, creator, memo_id)
    clock.now = datetime(2026, 9, 21, 0, 30, tzinfo=IST)  # still waiting
    record = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/delivery-record",
        headers=brand.headers,
    ).json()
    assert record["currently_overdue"] == 0
    clock.now = datetime(2026, 9, 21, 8, 0, tzinfo=IST)  # 23 hours after it was shown
    approve(client, brand, memo_id, draft["id"])
    clock.now = datetime(2026, 9, 21, 19, 0, tzinfo=IST)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
    )
    assert proof.status_code == 201, proof.text

    [campaign] = client.get("/api/v1/campaigns", headers=brand.headers).json()["items"]
    [deal] = client.get(
        f"/api/v1/campaigns/{campaign['id']}/report", headers=brand.headers
    ).json()["deals"]
    assert (deal["work_due_on"], deal["delivered_on_time"]) == ("2026-09-21", True)


def test_silence_through_the_window_moves_the_date_by_every_day_it_held(
    client, db, brand, creator, clock
):
    """The window's days and the day it was shown: the creator could post on none of them."""
    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-25"
    )
    draft = shown(client, creator, memo_id)
    window = db.get_one(DealMemo, memo_id).approval_window_days
    clock.now = deadline_of(db, memo_id, draft["id"]) + timedelta(days=1)

    expected = (date(2026, 9, 25) + timedelta(days=window + 1)).isoformat()
    assert memo_read(client, creator, memo_id)["work_due_on"] == expected


def test_every_round_the_brand_takes_is_added(client, brand, creator, clock):
    memo_id = accepted_memo(
        client, brand, creator, draft_review=True, content_due_on="2026-09-25"
    )
    first = shown(client, creator, memo_id)
    clock.advance(timedelta(days=2, hours=3))
    ask_changes(client, brand, memo_id, first["id"])
    clock.advance(timedelta(days=4))  # the creator's own time: not added
    second = shown(client, creator, memo_id)
    clock.advance(timedelta(days=3, hours=20))
    approve(client, brand, memo_id, second["id"])

    # 17 to 19 Sep, then 23 to 27 Sep: 2 + 4 days; the creator's 4 days between are theirs.
    assert memo_read(client, creator, memo_id)["work_due_on"] == "2026-10-01"


def test_a_deadline_passed_before_a_cancellation_is_recorded(
    client, db, brand, creator, memo_id, clock
):
    """Found by the second review: the clock's approval went unrecorded once the deal ended."""
    draft = shown(client, creator, memo_id)
    deadline = deadline_of(db, memo_id, draft["id"])
    memo = db.get_one(DealMemo, memo_id)
    memo.status = "cancelled"
    memo.cancellation_kind = "cancelled_by_brand"
    memo.cancelled_at = deadline + timedelta(hours=2)
    db.commit()
    clock.now = deadline + timedelta(days=1)

    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()

    assert (listed["status"], listed["auto_approved"]) == ("approved", True)
    assert listed["answer_by"] is None
    assert "draft_auto_approved" in [e["kind"] for e in entries(client, brand, memo_id)]
    assert told(db, creator, "draft_auto_approved") == []  # nothing to act on now


def test_a_cancelled_deals_waiting_draft_shows_no_answer_date(
    client, db, brand, creator, memo_id
):
    shown(client, creator, memo_id)
    memo = db.get_one(DealMemo, memo_id)
    memo.status = "cancelled"
    memo.cancellation_kind = "cancelled_by_brand"
    db.commit()

    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()

    assert (listed["status"], listed["answer_by"]) == ("submitted", None)


def test_an_approval_after_the_proof_is_refused(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    clock.now = deadline_of(db, memo_id, draft["id"]) + timedelta(minutes=1)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
    )
    assert proof.status_code == 201, proof.text

    assert_problem(
        approve(client, brand, memo_id, draft["id"]), 409, "draft_already_decided"
    )


def test_the_calendar_shows_when_a_waiting_draft_approves_itself(
    client, db, brand, creator, memo_id
):
    draft = shown(client, creator, memo_id)
    deadline = deadline_of(db, memo_id, draft["id"])

    ics = client.get(f"{MEMOS_URL}/{memo_id}/calendar.ics", headers=brand.headers).text

    assert "Draft approves itself" in ics
    assert deadline.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ") in ics


def test_a_cancellation_stops_the_date_moving(client, db, brand, creator, memo_id, clock):
    """Found by the third review: a cancelled deal's due date kept moving to the deadline."""
    shown(client, creator, memo_id)
    clock.advance(timedelta(days=1))
    memo = db.get_one(DealMemo, memo_id)
    due = memo.content_due_on
    memo.status = "cancelled"
    memo.cancellation_kind = "cancelled_by_brand"
    memo.cancelled_at = clock.now
    db.commit()
    clock.advance(timedelta(days=5))

    assert (
        memo_read(client, brand, memo_id)["work_due_on"]
        == (due + timedelta(days=1)).isoformat()
    )


def test_cancelled_at_the_very_deadline_the_clock_had_answered(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    deadline = deadline_of(db, memo_id, draft["id"])
    memo = db.get_one(DealMemo, memo_id)
    memo.status = "cancelled"
    memo.cancellation_kind = "cancelled_by_brand"
    memo.cancelled_at = deadline
    db.commit()
    clock.now = deadline + timedelta(days=1)

    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()

    assert (listed["status"], listed["auto_approved"]) == ("approved", True)


def test_the_calendar_drops_the_draft_event_once_answered(
    client, brand, creator, memo_id
):
    draft = shown(client, creator, memo_id)
    approve(client, brand, memo_id, draft["id"])

    ics = client.get(f"{MEMOS_URL}/{memo_id}/calendar.ics", headers=brand.headers).text

    assert "Draft approves itself" not in ics


def test_the_calendar_drops_a_draft_event_whose_moment_has_passed(
    client, db, brand, creator, memo_id, clock
):
    draft = shown(client, creator, memo_id)
    clock.now = deadline_of(db, memo_id, draft["id"]) + timedelta(minutes=1)

    ics = client.get(f"{MEMOS_URL}/{memo_id}/calendar.ics", headers=brand.headers).text

    assert "Draft approves itself" not in ics


def test_the_calendar_says_the_date_moves_while_a_draft_waits(
    client, brand, creator, memo_id, clock
):
    shown(client, creator, memo_id)
    clock.advance(timedelta(days=2))

    ics = client.get(f"{MEMOS_URL}/{memo_id}/calendar.ics", headers=brand.headers).text

    assert "add this file again once it is answered" in ics.replace("\r\n ", "")


def test_a_list_that_settles_costs_the_same_queries_however_many_rounds(
    client, db, brand, creator, clock
):
    """Found by the third review: settling expired every row, read back one at a time."""
    from tests.query_counts import queries_for

    def overdue_list(rounds: int) -> int:
        memo_id = accepted_memo(client, brand, creator, draft_review=True)
        for _ in range(rounds - 1):
            earlier = shown(client, creator, memo_id)
            ask_changes(client, brand, memo_id, earlier["id"])
        last = shown(client, creator, memo_id)
        saved = clock.now
        clock.now = deadline_of(db, memo_id, last["id"]) + timedelta(minutes=1)
        count = queries_for(client, drafts_url(memo_id), creator.headers)
        clock.now = saved
        return count

    assert overdue_list(5) == overdue_list(1)
