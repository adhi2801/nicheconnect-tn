"""Every downgrade that would destroy unrecoverable data refuses while it exists.

database.md section 6: losing such data must be a deliberate act, never a
side effect of a rollback. Ten migrations refuse. Until 14 October 2026 each
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
from tests.factories import create_account

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Every migration whose downgrade refuses, by revision. A test below fails if
# a migration starts or stops refusing without this list changing.
REFUSING = {
    "0942f3ef82c3": "admin accounts",
    "2c3bf71783d2": "invitations",
    "429278d02ad2": "decline dates, change requests, first answers",
    "8c960d1db341": "how accounts arrived",
    "b3172a361a61": "proof readings on the deal record",
    "c45a9831e0c9": "proof files",
    "e39beab4e841": "creator UPI IDs",
    "e591b300cca7": "blocks",
    "f0ec9547afcc": "reports and suspensions for impersonation or intimate content",
    "f276d2c6ce1e": "cleaned proof files on the deal record",
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
