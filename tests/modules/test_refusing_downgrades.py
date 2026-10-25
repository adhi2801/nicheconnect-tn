"""Every downgrade that would destroy unrecoverable data refuses while it exists.

database.md section 6: losing such data must be a deliberate act, never a
side effect of a rollback. Eighteen migrations refuse. Until 14 October 2026 each
refusal had been proven only by hand, in the session that wrote it
(database.md gap 6, item 98); a later edit to one could have let a rollback
drop a deal's record or a person's block without anyone noticing.

Each test writes the data a migration guards, inside the test's rolled-back
transaction, then runs that migration's real `downgrade()` on the same
connection and watches it refuse. Where the refusal counts rows, the count
must include the row written here, so a table that already held rows cannot
make the test pass by luck. The refusal comes before any schema change, and
the transaction is rolled back regardless, so nothing is ever dropped.
"""

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.deal_memo import record_service
from app.modules.deal_memo.models import DealMemo
from tests.deal_flow import accepted_memo, brand_user, creator_user
from tests.factories import build_brand, create_account, unique_test_phone

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Every migration whose downgrade refuses, by revision. A test below fails if
# a migration starts or stops refusing without this list changing.
REFUSING = {
    "0942f3ef82c3": "admin accounts",
    "4a2f6982641f": "takedowns, and the admin log's entries about them",
    "2c3bf71783d2": "invitations",
    "429278d02ad2": "decline dates, change requests, first answers",
    "8c960d1db341": "how accounts arrived",
    "b3172a361a61": "proof readings on the deal record",
    "c45a9831e0c9": "proof files",
    "e39beab4e841": "creator UPI IDs",
    "e591b300cca7": "blocks",
    "f0ec9547afcc": "reports and suspensions for impersonation or intimate content",
    "f276d2c6ce1e": "cleaned proof files on the deal record",
    "90b4db0fd32a": "admins' authenticators, set up or waiting",
    "8a974ebde203": "brands' verified domains",
    "44fc99b873a7": "new UPI IDs waiting their 24 hours, each with its consent",
    "d18c285488f0": "new phone numbers waiting their 72 hours, each proven by two codes",
    "8bfc55b8e5fe": "new phone numbers waiting 7 days without the current number",
    "928b6af0172c": "data exports being prepared, or with a file still stored",
    "ceeda50f8c0b": "passkeys guarding people's accounts",
    "de322e936678": "notices telling people one of their sessions was ended",
    "82bb81b5eed4": "admins' clearances of look-alike brand names, and their log entries",
    "b7e026caa4a9": "accounts waiting to be deleted, or deleted, which lack a number",
    "8b6662af4839": "counter-offers on quotes, both sides' record of the negotiation",
}


def migration(revision: str) -> ModuleType:
    (path,) = VERSIONS.glob(f"{revision}_*.py")
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refusal(db: Session, revision: str) -> str:
    """Run the migration's downgrade on the test's connection; return why it refused."""
    context = MigrationContext.configure(db.connection())
    with pytest.raises(RuntimeError) as refused, Operations.context(context):
        migration(revision).downgrade()
    return str(refused.value)


def count(db: Session, sql: str) -> int:
    return int(db.execute(text(sql)).scalar_one())


def test_the_list_is_every_refusing_downgrade():
    refusing = {
        path.name.split("_", 1)[0]
        for path in VERSIONS.glob("*.py")
        if "raise RuntimeError"
        in path.read_text(encoding="utf-8").split("def downgrade", 1)[-1]
    }

    assert refusing == set(REFUSING)


def test_admin_accounts(db):
    before = count(db, "SELECT count(*) FROM account WHERE role = 'admin'")
    create_account(db, "admin")
    db.flush()

    assert f"{before + 1} admin account(s) exist" in refusal(db, "0942f3ef82c3")


def test_invitations(client, db, clock):
    before = count(db, "SELECT count(*) FROM application WHERE origin = 'invited'")
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    campaign_id = client.post(
        "/api/v1/campaigns",
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
    client.post(f"/api/v1/campaigns/{campaign_id}/publish", headers=brand.headers)
    creator_id = db.execute(
        text("SELECT id FROM creator WHERE account_id = :a"), {"a": creator.account_id}
    ).scalar_one()
    invited = client.post(
        f"/api/v1/campaigns/{campaign_id}/invitations",
        json={"creator_id": str(creator_id)},
        headers=brand.headers,
    )
    assert invited.status_code == 201, invited.text

    assert f"{before + 1} invitation(s) exist" in refusal(db, "2c3bf71783d2")


def test_decline_dates_change_requests_and_first_answers(client, db, clock):
    before = count(
        db,
        "SELECT (SELECT count(*) FROM deal_memo WHERE declined_at IS NOT NULL"
        " OR change_request_message IS NOT NULL)"
        " + (SELECT count(*) FROM application WHERE first_answered_at IS NOT NULL)",
    )
    # An accepted deal: its application was answered once, so one row.
    accepted_memo(client, brand_user(db, clock), creator_user(db, clock))

    assert f"{before + 1} rows hold" in refusal(db, "429278d02ad2")


def test_how_accounts_arrived(db):
    before = count(db, "SELECT count(*) FROM account_attribution")
    account = create_account(db, "creator")
    db.execute(
        text("INSERT INTO account_attribution (account_id, source) VALUES (:a, 'other')"),
        {"a": account.id},
    )

    assert f"{before + 1} accounts have their arrival recorded" in refusal(
        db, "8c960d1db341"
    )


@pytest.mark.parametrize(
    ("revision", "kind"),
    [("b3172a361a61", "proof_results_read"), ("f276d2c6ce1e", "proof_file_cleaned")],
)
def test_entries_on_the_deal_record(client, db, clock, revision, kind):
    before = count(db, f"SELECT count(*) FROM deal_record_entry WHERE kind = '{kind}'")  # noqa: S608 - a fixed kind from the parameters above
    memo_id = accepted_memo(client, brand_user(db, clock), creator_user(db, clock))
    memo = db.get(DealMemo, uuid.UUID(memo_id))
    assert memo is not None
    record_service.append(db, memo, kind=kind, actor_role="system", now=clock.now)
    db.flush()

    assert f"{before + 1} {kind} record entries exist" in refusal(db, revision)


def test_proof_files(client, db, clock):
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand_user(db, clock), creator)
    db.execute(
        text(
            "INSERT INTO proof_file (deal_memo_id, uploader_account_id, storage_key,"
            " content_type, size_bytes, sha256)"
            " VALUES (:m, :a, 'proof-files/test', 'image/png', 1, repeat('a', 64))"
        ),
        {"m": memo_id, "a": creator.account_id},
    )

    assert "proof files exist" in refusal(db, "c45a9831e0c9")


def test_creator_upi_ids(db, clock):
    before = count(db, "SELECT count(*) FROM creator_upi")
    creator = creator_user(db, clock)
    db.execute(
        text(
            "INSERT INTO creator_upi (creator_id, upi_id, consented_at, notice_version)"
            " SELECT id, 'priya.reels@okaxis', now(), 'v1' FROM creator WHERE account_id = :a"
        ),
        {"a": creator.account_id},
    )

    assert f"{before + 1} creator UPI ID(s) exist" in refusal(db, "e39beab4e841")


def test_blocks(db):
    before = count(db, "SELECT count(*) FROM account_block")
    blocker, blocked = create_account(db, "brand"), create_account(db, "creator")
    db.execute(
        text(
            "INSERT INTO account_block (blocker_account_id, blocked_account_id) VALUES (:a, :b)"
        ),
        {"a": blocker.id, "b": blocked.id},
    )

    assert f"{before + 1} block(s) exist" in refusal(db, "e591b300cca7")


IMPERSONATION_OR_INTIMATE = (
    "SELECT (SELECT count(*) FROM report"
    " WHERE category IN ('impersonation', 'intimate_content'))"
    " + (SELECT count(*) FROM account"
    " WHERE suspension_reason IN ('impersonation', 'intimate_content'))"
)


def test_reports_for_impersonation_or_intimate_content(db):
    before = count(db, IMPERSONATION_OR_INTIMATE)
    reporter = create_account(db, "brand")
    db.execute(
        text(
            "INSERT INTO report (reporter_account_id, subject_kind, subject_id, category,"
            " status, created_at, due_at) VALUES (:a, 'creator', :s, 'impersonation',"
            " 'open', now(), now() + interval '2 hours')"
        ),
        {"a": reporter.id, "s": uuid.uuid4()},
    )

    assert f"{before + 1} reports or suspensions" in refusal(db, "f0ec9547afcc")


def test_suspensions_for_intimate_content(db):
    before = count(db, IMPERSONATION_OR_INTIMATE)
    account = create_account(db, "creator")
    db.execute(
        text(
            "UPDATE account SET suspended_at = now(), suspension_reason = 'intimate_content'"
            " WHERE id = :a"
        ),
        {"a": account.id},
    )

    assert f"{before + 1} reports or suspensions" in refusal(db, "f0ec9547afcc")


TAKEDOWNS = (
    "SELECT (SELECT count(*) FROM takedown) + (SELECT count(*) FROM admin_action"
    " WHERE action IN ('withhold', 'lift_withhold'))"
)


def test_takedowns(db):
    """The IT Rules ask us to keep what was withheld and its record (item 52)."""
    before = count(db, TAKEDOWNS)
    admin, owner = create_account(db, "admin"), create_account(db, "brand")
    db.execute(
        text(
            "INSERT INTO takedown (subject_kind, subject_id, owner_account_id, basis,"
            " issued_by, order_reference, received_at, due_at, withheld_at,"
            " withheld_by_account_id, preserved)"
            " VALUES ('brand', :s, :o, 'court_order', 'High Court of Madras',"
            " 'WP 1 of 2026', now() - interval '1 hour', now() + interval '2 hours',"
            " now(), :a, '{}')"
        ),
        {"s": uuid.uuid4(), "o": owner.id, "a": admin.id},
    )

    assert f"{before + 1} takedowns or admin log entries" in refusal(db, "4a2f6982641f")


def test_admin_log_entries_about_takedowns(db):
    """The log never loses an entry, so its new actions cannot be listed away."""
    before = count(db, TAKEDOWNS)
    admin = create_account(db, "admin")
    db.execute(
        text(
            "INSERT INTO admin_action (admin_account_id, action, note)"
            " VALUES (:a, 'lift_withhold', 'The order was set aside.')"
        ),
        {"a": admin.id},
    )

    assert f"{before + 1} takedowns or admin log entries" in refusal(db, "4a2f6982641f")


def test_admins_authenticators(db):
    before = count(db, "SELECT count(*) FROM totp_factor")
    admin = create_account(db, "admin")
    db.flush()
    db.execute(
        text(
            "INSERT INTO totp_factor (account_id, ticket_hash, ticket_expires_at)"
            " VALUES (:account_id, :ticket_hash, now() + interval '15 minutes')"
        ),
        {"account_id": admin.id, "ticket_hash": "0" * 64},
    )

    assert f"{before + 1} admin authenticators" in refusal(db, "90b4db0fd32a")


def test_brands_verified_domains(db):
    before = count(db, "SELECT count(*) FROM brand_domain WHERE status = 'verified'")
    brand = build_brand(db, email=f"domain-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    db.execute(
        text(
            "INSERT INTO brand_domain (brand_id, domain, token, status, claimed_at,"
            " token_expires_at, verified_at, last_checked_at, last_result)"
            " VALUES (:brand, :domain, repeat('a', 26), 'verified', now(),"
            " now() + interval '7 days', now(), now(), 'found')"
        ),
        {"brand": brand.id, "domain": f"d{uuid.uuid4().hex[:12]}.in"},
    )

    assert f"{before + 1} brands have a verified domain" in refusal(db, "8a974ebde203")


def test_new_upi_ids_waiting(db, clock):
    before = count(db, "SELECT count(*) FROM creator_upi_change")
    creator = creator_user(db, clock)
    db.execute(
        text(
            "INSERT INTO creator_upi_change "
            "(creator_id, upi_id, consented_at, notice_version, usable_at) "
            "SELECT id, 'priya.new@okaxis', now(), 'v1', now() + interval '24 hours' "
            "FROM creator WHERE account_id = :a"
        ),
        {"a": creator.account_id},
    )

    assert f"{before + 1} creators have a new UPI ID waiting" in refusal(
        db, "44fc99b873a7"
    )


def test_new_phone_numbers_waiting(db):
    before = count(db, "SELECT count(*) FROM account_phone_change")
    account = create_account(db, "brand")
    db.execute(
        text(
            "INSERT INTO account_phone_change "
            "(account_id, new_phone, requested_at, takes_effect_at) "
            "VALUES (:a, :p, now(), now() + interval '72 hours')"
        ),
        {"a": account.id, "p": unique_test_phone()},
    )

    assert f"{before + 1} accounts are waiting to move to a new phone number" in (
        refusal(db, "d18c285488f0")
    )


def test_new_phone_numbers_waiting_without_the_current_number(db):
    before = count(
        db, "SELECT count(*) FROM account_phone_change WHERE without_current_number"
    )
    account = create_account(db, "creator")
    db.execute(
        text(
            "INSERT INTO account_phone_change (account_id, new_phone, requested_at, "
            "takes_effect_at, without_current_number) "
            "VALUES (:a, :p, now(), now() + interval '7 days', true)"
        ),
        {"a": account.id, "p": unique_test_phone()},
    )

    assert f"{before + 1} accounts are waiting to move to a new phone number without" in (
        refusal(db, "8bfc55b8e5fe")
    )


def test_data_exports_with_a_file_still_stored(db):
    before = count(
        db,
        "SELECT count(*) FROM data_export WHERE failed_at IS NULL "
        "AND (ready_at IS NULL OR file_deleted_at IS NULL)",
    )
    account = create_account(db, "creator")
    db.execute(
        text("INSERT INTO data_export (account_id, requested_at) VALUES (:a, now())"),
        {"a": account.id},
    )

    assert f"{before + 1} data exports are being prepared or have a file" in refusal(
        db, "928b6af0172c"
    )


def test_passkeys(db):
    before = count(db, "SELECT count(*) FROM passkey")
    account = create_account(db, "creator")
    db.execute(
        text(
            "INSERT INTO passkey (account_id, credential_id, public_key, sign_count, "
            "aaguid, backup_eligible, backup_state, name) VALUES (:a, :c, :k, 0, "
            ":g, true, true, 'My phone')"
        ),
        {
            "a": account.id,
            "c": uuid.uuid4().bytes,
            "k": b"\xa1\x01\x02",
            "g": uuid.UUID(int=0),
        },
    )

    assert f"{before + 1} passkeys are on people's accounts" in refusal(
        db, "ceeda50f8c0b"
    )


def test_notices_that_a_session_was_ended(db):
    before = count(
        db, "SELECT count(*) FROM notification WHERE notification_type = 'session_ended'"
    )
    account = create_account(db, "creator")
    db.execute(
        text(
            "INSERT INTO notification (account_id, notification_type, details) "
            "VALUES (:a, 'session_ended', '{}')"
        ),
        {"a": account.id},
    )

    assert f"{before + 1} notices tell people that one of their sessions" in refusal(
        db, "de322e936678"
    )


def test_clearances_of_look_alike_names(db):
    before = count(db, "SELECT count(*) FROM brand WHERE name_cleared IS NOT NULL")
    brand = build_brand(db, email=f"r-{uuid.uuid4().hex[:10]}@example.com")
    db.add(brand)
    db.flush()
    db.execute(
        text(
            "UPDATE brand SET name_cleared = name, name_cleared_at = now() WHERE id = :b"
        ),
        {"b": brand.id},
    )

    assert f"{before + 1} brands hold an admin's clearance" in refusal(db, "82bb81b5eed4")


def test_log_entries_of_clearing_names(db):
    before = count(
        db,
        "SELECT count(*) FROM admin_action WHERE action IN"
        " ('clear_brand_name', 'withdraw_brand_name_clearance')",
    )
    admin = create_account(db, "admin")
    db.execute(
        text(
            "INSERT INTO admin_action (admin_account_id, action, note)"
            " VALUES (:a, 'clear_brand_name', 'checked')"
        ),
        {"a": admin.id},
    )

    assert f"{before + 1} admin log entries record clearing" in refusal(
        db, "82bb81b5eed4"
    )


def test_accounts_asked_to_be_deleted(db):
    before = count(
        db, "SELECT count(*) FROM account WHERE deletion_requested_at IS NOT NULL"
    )
    account = create_account(db, "creator")
    db.execute(
        text(
            "UPDATE account SET deletion_requested_at = now(),"
            " deletion_takes_effect_at = now() + interval '30 days' WHERE id = :a"
        ),
        {"a": account.id},
    )

    assert f"{before + 1} accounts have asked to be deleted" in refusal(
        db, "b7e026caa4a9"
    )


def test_counter_offers(client, db, clock):
    before = count(db, "SELECT count(*) FROM quote_offer")
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = client.post(
        "/api/v1/campaigns",
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
    client.post(f"/api/v1/campaigns/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"/api/v1/campaigns/{campaign_id}/applications",
        json={"pitch": "I run a Madurai street-food page with 12,000 followers."},
        headers=creator.headers,
    ).json()["id"]
    offered = client.post(
        f"/api/v1/applications/{application_id}/offers",
        json={"amount_paise": 600_000},
        headers=brand.headers,
    )
    assert offered.status_code == 201, offered.text

    assert f"{before + 1} quote offers exist" in refusal(db, "8b6662af4839")
