"""Database rules that no test had broken until 14 October 2026.

database.md section 3: every rule the database holds has a test that writes
the forbidden row with raw SQL and watches the database refuse it, so a bug
in the code, a script or a hand-written query still cannot break it. A
reading of the catalogue that day found 21 rules no test named
(tests/test_schema_rules.py now fails if one appears again).

Each test starts from rows a real deal made through the API, then changes
one column with raw SQL, inside a savepoint, so exactly one rule is broken
and the error must name that rule.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.deal_flow import LINK, MEMOS_URL, accepted_memo, brand_user, creator_user
from tests.factories import create_account

RRN = "412345678901"
REASON = "The payment was marked sent on 8 September but nothing has reached my account."


@pytest.fixture
def deal(client: TestClient, db: Session, clock) -> dict[str, uuid.UUID]:
    """A deal with approved work, a payment marked sent, and a dispute."""
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    paid = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=brand.headers,
    )
    disputed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json={"reason": REASON},
        headers=creator.headers,
    )
    assert (approved.status_code, paid.status_code, disputed.status_code) == (
        200,
        200,
        201,
    ), disputed.text

    def one(sql: str) -> uuid.UUID:
        return db.execute(text(sql), {"memo": memo_id}).scalar_one()

    return {
        "brand_account": brand.account_id,
        "creator_account": creator.account_id,
        "application": one("SELECT application_id FROM deal_memo WHERE id = :memo"),
        "proof": uuid.UUID(proof_id),
        "dispute": one(
            "SELECT d.id FROM dispute d JOIN payment_status p ON p.id = d.payment_status_id "
            "WHERE p.deal_memo_id = :memo"
        ),
        "dispute_event": one(
            "SELECT e.id FROM dispute_event e JOIN dispute d ON d.id = e.dispute_id "
            "JOIN payment_status p ON p.id = d.payment_status_id "
            "WHERE p.deal_memo_id = :memo LIMIT 1"
        ),
        "notification": one(
            "SELECT n.id FROM notification n JOIN deal_memo m "
            "ON m.application_id = n.application_id WHERE m.id = :memo LIMIT 1"
        ),
    }


def assert_refused(db: Session, statement: str, rule: str, row: uuid.UUID) -> None:
    """The statement is refused, and the refusal names this rule.

    Statements are written whole, never assembled from strings (ruff S608).
    """
    with pytest.raises(IntegrityError, match=rule), db.begin_nested():
        db.execute(text(statement), {"id": row})


# --- application ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        ("UPDATE application SET pitch = 'Too short.' WHERE id = :id", "pitch_length"),
        (
            "UPDATE application SET pitch = repeat('x', 1001) WHERE id = :id",
            "pitch_length",
        ),
        (
            "UPDATE application SET quoted_amount_paise = 0 WHERE id = :id",
            "quoted_amount_positive",
        ),
        (
            "UPDATE application SET rejection_note = repeat('x', 501) WHERE id = :id",
            "rejection_note_length",
        ),
        # Accepted, yet carrying a reason it was rejected.
        (
            "UPDATE application SET rejection_reason = 'budget_mismatch' WHERE id = :id",
            "rejection_reason_matches_status",
        ),
        # The same creator applying to the same campaign a second time.
        (
            "INSERT INTO application (campaign_id, creator_id, origin, status, pitch) "
            "SELECT campaign_id, creator_id, origin, 'submitted', pitch "
            "FROM application WHERE id = :id",
            "uq_application_campaign_creator",
        ),
    ],
)
def test_an_application_breaking_a_rule_is_refused(db, deal, statement, rule):
    assert_refused(db, statement, rule, deal["application"])


# --- proof of work ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        (
            "UPDATE deliverable_proof SET approved_at = NULL WHERE id = :id",
            "approved_at_matches_status",
        ),
        (
            "UPDATE deliverable_proof SET status = 'revision_requested', "
            "approved_at = NULL, auto_approved = true WHERE id = :id",
            "auto_approved_is_approved",
        ),
        (
            "UPDATE deliverable_proof "
            "SET content_url = 'http://www.instagram.com/reel/abc123/' WHERE id = :id",
            "content_url_https",
        ),
        (
            "UPDATE deliverable_proof SET revision_note = repeat('x', 1001) WHERE id = :id",
            "revision_note_length",
        ),
    ],
)
def test_proof_breaking_a_rule_is_refused(db, deal, statement, rule):
    assert_refused(db, statement, rule, deal["proof"])


# --- disputes -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        ("UPDATE dispute SET opened_by = 'admin' WHERE id = :id", "opened_by_allowed"),
        (
            "UPDATE dispute SET outcome = 'won', closed_at = now() WHERE id = :id",
            "outcome_allowed",
        ),
        (
            "UPDATE dispute SET closed_at = now() WHERE id = :id",
            "outcome_matches_closed_at",
        ),
        ("UPDATE dispute SET reason = 'Not paid yet.' WHERE id = :id", "reason_length"),
        ("UPDATE dispute SET reason = repeat('x', 2001) WHERE id = :id", "reason_length"),
    ],
)
def test_a_dispute_breaking_a_rule_is_refused(db, deal, statement, rule):
    assert_refused(db, statement, rule, deal["dispute"])


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        # Events are sealed (item 99), so each rule is broken by a new one,
        # copied from a real event with one thing wrong.
        (
            "INSERT INTO dispute_event (dispute_id, actor_role, kind, evidence_url) "
            "SELECT dispute_id, actor_role, 'evidence', "
            "'http://drive.google.com/file/d/1/view' FROM dispute_event WHERE id = :id",
            "evidence_url_is_https",
        ),
        (
            "INSERT INTO dispute_event (dispute_id, actor_role, kind) "
            "SELECT dispute_id, actor_role, 'response' FROM dispute_event WHERE id = :id",
            "says_something",
        ),
    ],
)
def test_a_dispute_event_breaking_a_rule_is_refused(db, deal, statement, rule):
    assert_refused(db, statement, rule, deal["dispute_event"])


# The owner: the app's own login is refused by permission before the trigger
# this shows is reached (item 97, tests/owner.py).
@pytest.mark.owner
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE dispute_event SET note = 'Rewritten later.' WHERE id = :id",
        "DELETE FROM dispute_event WHERE id = :id",
    ],
)
def test_a_dispute_event_once_written_never_changes(db, deal, statement):
    """Item 99: the timeline is sealed like the deal record (D-057)."""
    with (
        pytest.raises(IntegrityError, match="dispute_event is append-only"),
        db.begin_nested(),
    ):
        db.execute(text(statement), {"id": deal["dispute_event"]})


# --- notifications ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        # A list, not an object.
        "UPDATE notification SET details = '[]'::jsonb WHERE id = :id",
        # An object too big to be a notification's few facts.
        "UPDATE notification "
        "SET details = jsonb_build_object('note', repeat('x', 2000)) WHERE id = :id",
    ],
)
def test_notification_details_must_be_a_small_object(db, deal, statement):
    assert_refused(db, statement, "details_small_object", deal["notification"])


@pytest.fixture
def preference(db: Session) -> uuid.UUID:
    account = create_account(db, "creator")
    db.execute(
        text("INSERT INTO notification_preference (account_id) VALUES (:a)"),
        {"a": account.id},
    )
    return account.id


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        (
            "UPDATE notification_preference SET digest = 'weekly' WHERE account_id = :id",
            "digest_allowed",
        ),
        (
            "UPDATE notification_preference SET digest_hour = 24 WHERE account_id = :id",
            "digest_hour_valid",
        ),
        (
            "UPDATE notification_preference SET digest_hour = -1 WHERE account_id = :id",
            "digest_hour_valid",
        ),
        (
            "UPDATE notification_preference SET quiet_from = '22:00', "
            "quiet_until = '22:00' WHERE account_id = :id",
            "quiet_hours_not_empty",
        ),
    ],
)
def test_a_notification_preference_breaking_a_rule_is_refused(
    db, preference, statement, rule
):
    assert_refused(db, statement, rule, preference)


# --- attribution --------------------------------------------------------------------------


@pytest.fixture
def attribution(db: Session) -> uuid.UUID:
    account = create_account(db, "creator")
    db.execute(
        text("INSERT INTO account_attribution (account_id, source) VALUES (:a, 'other')"),
        {"a": account.id},
    )
    return account.id


@pytest.mark.parametrize(
    ("statement", "rule"),
    [
        (
            "UPDATE account_attribution SET source = 'television' WHERE account_id = :id",
            "source_allowed",
        ),
        (
            "UPDATE account_attribution "
            "SET campaign_tag = 'Pongal Launch' WHERE account_id = :id",
            "campaign_tag_format",
        ),
    ],
)
def test_attribution_breaking_a_rule_is_refused(db, attribution, statement, rule):
    assert_refused(db, statement, rule, attribution)
