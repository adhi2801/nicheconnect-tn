"""The deal record end to end: real deals over HTTP, then the record (D-057).

The tests that matter: every step writes exactly one entry, a refused step
writes none, nothing typed ever appears, only the two parties can read it,
and the seals can be checked from the JSON alone, without our code.
"""

import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.record_router import READ_LIMIT
from tests.deal_flow import (
    AGREED_DUE_ON,
    LINK,
    MEMOS_URL,
    PITCH,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)

REFERENCE = "412345678901"
DOMAIN = bytes([*b"deal-record/v1", 10])  # the prefix, ending in a newline
CAMPAIGNS_URL = "/api/v1/campaigns"
DELIVERABLES = "3 Instagram reels, 1 story set."


def draft_memo(client, brand: User, creator: User) -> str:
    """A memo the brand has drafted and not yet sent."""
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
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    response = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": DELIVERABLES,
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def record_of(client, user: User, memo_id: str) -> dict:
    response = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def kinds(record: dict) -> list[str]:
    return [entry["kind"] for entry in record["entries"]]


def submit_proof(client, creator: User, memo_id: str) -> str:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def paid_deal(client, brand: User, creator: User) -> str:
    """Sent, accepted, delivered, approved, paid and confirmed."""
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit_proof(client, creator, memo_id)
    for response in (
        client.post(
            f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
        ),
        client.post(
            f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
            json={"method": "upi", "reference": REFERENCE},
            headers=brand.headers,
        ),
        client.post(f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers),
    ):
        assert response.status_code == 200, response.text
    return memo_id


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


# --- what it records -------------------------------------------------------------


def test_a_whole_deal_is_recorded_step_by_step(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)

    record = record_of(client, brand, memo_id)

    assert kinds(record) == [
        "memo_sent",
        "memo_accepted",
        "proof_submitted",
        "proof_approved",
        "payment_opened",
        "payment_marked_paid",
        "payment_confirmed",
    ]
    assert [e["actor_role"] for e in record["entries"]] == [
        "brand",
        "creator",
        "creator",
        "brand",
        "system",
        "brand",
        "creator",
    ]
    assert [e["sequence"] for e in record["entries"]] == list(range(1, 8))
    assert record["intact"] is True
    assert record["terms_unchanged_since_accepted"] is True
    assert record["latest_seal"] == record["entries"][-1]["seal"]


def test_the_figures_people_argue_about_are_in_plain_numbers(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)

    entries = {e["kind"]: e for e in record_of(client, brand, memo_id)["entries"]}

    assert entries["memo_accepted"]["facts"]["fee_amount_paise"] == 800_000
    assert entries["memo_accepted"]["facts"]["content_due_on"] == "2026-12-31"
    assert entries["payment_opened"]["facts"]["amount_paise"] == 800_000
    assert entries["payment_marked_paid"]["facts"]["method"] == "upi"


def test_nothing_anyone_typed_appears_only_its_fingerprint(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)

    record = record_of(client, brand, memo_id)
    text = json.dumps(record)

    for typed in (REFERENCE, LINK, DELIVERABLES):
        assert typed not in text
    marked = next(e for e in record["entries"] if e["kind"] == "payment_marked_paid")
    assert (
        marked["facts"]["reference_sha256"]
        == hashlib.sha256(REFERENCE.encode()).hexdigest()
    )
    submitted = next(e for e in record["entries"] if e["kind"] == "proof_submitted")
    assert (
        submitted["facts"]["content_url_sha256"]
        == hashlib.sha256(LINK.encode()).hexdigest()
    )


def test_work_approved_at_the_deadline_shows_both_times(client, clock, brand, creator):
    """Took effect at the end of the window; written down when noticed."""
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit_proof(client, creator, memo_id)
    submitted_at = clock.now
    clock.advance(timedelta(days=10))

    # Reading the submissions is what settles an overdue one (D-025).
    listed = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers)
    assert listed.status_code == 200, listed.text
    record = record_of(client, brand, memo_id)

    auto = next(e for e in record["entries"] if e["kind"] == "proof_auto_approved")
    assert auto["actor_role"] == "system"
    assert auto["facts"] == {"proof_id": proof_id}
    assert auto["occurred_at"] < auto["recorded_at"]
    assert auto["occurred_at"].startswith(
        (submitted_at + timedelta(days=7)).date().isoformat()
    )
    assert kinds(record)[-1] == "payment_opened"


def test_a_dispute_is_on_the_record(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit_proof(client, creator, memo_id)
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    url = f"{MEMOS_URL}/{memo_id}/payment/dispute"
    reason = "The payment was due last week and nothing has arrived yet."
    for response in (
        client.post(url, json={"reason": reason}, headers=creator.headers),
        client.post(
            f"{url}/entries",
            json={"note": "We paid on the 3rd; checking with our bank."},
            headers=brand.headers,
        ),
        client.post(
            f"{url}/close", json={"outcome": "resolved_paid"}, headers=creator.headers
        ),
    ):
        assert response.status_code in (200, 201), response.text

    record = record_of(client, creator, memo_id)

    assert kinds(record)[-3:] == [
        "dispute_opened",
        "dispute_entry_added",
        "dispute_closed",
    ]
    assert reason not in json.dumps(record)
    assert record["entries"][-1]["facts"]["outcome"] == "resolved_paid"
    assert record["intact"] is True


def test_a_resend_after_changes_is_recorded_with_the_new_terms(client, brand, creator):
    memo_id = draft_memo(client, brand, creator)
    for response in (
        client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers),
        client.post(
            f"{MEMOS_URL}/{memo_id}/request-change",
            json={"message": "Could the fee be a little higher?"},
            headers=creator.headers,
        ),
        client.patch(
            f"{MEMOS_URL}/{memo_id}",
            json={"fee_amount_paise": 900_000},
            headers=brand.headers,
        ),
        client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers),
        client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers),
    ):
        assert response.status_code == 200, response.text

    record = record_of(client, brand, memo_id)

    assert kinds(record) == [
        "memo_sent",
        "memo_change_requested",
        "memo_sent",
        "memo_accepted",
    ]
    first, _, resent, accepted = (e["facts"] for e in record["entries"])
    assert first["fee_amount_paise"] == 800_000
    assert resent["fee_amount_paise"] == accepted["fee_amount_paise"] == 900_000
    assert first["terms_sha256"] != resent["terms_sha256"] == accepted["terms_sha256"]
    # The creator's own words are not on the record, not even as a fingerprint.
    assert record["entries"][1]["facts"] == {}


def test_a_refused_step_writes_nothing(client, db, brand, creator):
    memo_id = paid_deal(client, brand, creator)
    before = db.scalar(select(func.count()).select_from(DealRecordEntry))

    again = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": REFERENCE},
        headers=brand.headers,
    )

    assert again.status_code == 409
    assert db.scalar(select(func.count()).select_from(DealRecordEntry)) == before


def test_a_draft_cancelled_before_anyone_saw_it_has_no_record(client, brand, creator):
    """A draft is the brand's own workspace; it was never a deal."""
    memo_id = draft_memo(client, brand, creator)
    cancelled = client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)
    assert cancelled.status_code == 200, cancelled.text

    record = record_of(client, brand, memo_id)

    assert record["entries"] == []
    assert record["latest_seal"] is None
    assert record["intact"] is True


def test_a_cancellation_after_sending_says_how_it_ended(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)

    last = record_of(client, brand, memo_id)["entries"][-1]
    assert last["kind"] == "memo_cancelled"
    assert last["facts"] == {"cancellation_kind": "withdrawn_early"}


# --- checking it without our code -------------------------------------------------


def check_seals(entries: list[dict], memo_id: str) -> str:
    """The script in docs/DEAL_RECORD_VERIFY.md, using only the JSON given."""
    previous = "00" * 32
    for entry in sorted(entries, key=lambda e: e["sequence"]):
        body = {
            "deal_memo_id": entry.get("deal_memo_id") or memo_id,
            "sequence": entry["sequence"],
            "kind": entry["kind"],
            "actor_role": entry["actor_role"],
            "actor_account_sha256": entry["actor_account_sha256"],
            "occurred_at": entry["occurred_at"],
            "recorded_at": entry["recorded_at"],
            "facts": entry["facts"],
        }
        canonical = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        seal = hashlib.sha256(DOMAIN + bytes.fromhex(previous) + canonical).hexdigest()
        assert entry["previous_seal"] == previous, entry["sequence"]
        assert entry["seal"] == seal, entry["sequence"]
        previous = seal
    return previous


def test_the_seals_check_out_from_the_json_alone(client, brand, creator):
    """Nothing but the response: neither side is shown the other's account id."""
    memo_id = paid_deal(client, brand, creator)
    record = record_of(client, creator, memo_id)

    assert check_seals(record["entries"], record["deal_memo_id"]) == record["latest_seal"]


def test_the_seals_check_out_from_the_export_file_alone(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)
    rows = client.get("/api/v1/me/export", headers=brand.headers).json()["data"][
        "deal_record"
    ]

    latest = check_seals([r for r in rows if r["deal_memo_id"] == memo_id], memo_id)

    assert latest == record_of(client, brand, memo_id)["latest_seal"]


def test_each_side_can_recognise_its_own_entries(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)
    record = record_of(client, creator, memo_id)
    mine = hashlib.sha256(str(creator.account_id).encode()).hexdigest()

    by_me = [e["kind"] for e in record["entries"] if e["actor_account_sha256"] == mine]

    assert by_me == ["memo_accepted", "proof_submitted", "payment_confirmed"]
    assert str(brand.account_id) not in json.dumps(record)


def test_times_come_out_in_the_spelling_the_seal_uses(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    entry = record_of(client, brand, memo_id)["entries"][0]

    assert entry["occurred_at"].endswith("Z")
    assert len(entry["occurred_at"]) == len("2026-09-26T06:30:00.000000Z")


# --- who may read it ------------------------------------------------------------


def test_the_creator_reads_the_same_record(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)

    assert record_of(client, creator, memo_id) == record_of(client, brand, memo_id)


def test_anyone_else_gets_not_found(client, db, clock, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    for stranger in (brand_user(db, clock), creator_user(db, clock)):
        response = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=stranger.headers)
        assert response.status_code == 404
        assert response.json()["code"] == "memo_not_found"


def test_an_unknown_memo_is_not_found(client, brand):
    response = client.get(f"{MEMOS_URL}/{uuid.uuid4()}/record", headers=brand.headers)

    assert response.status_code == 404


def test_it_is_not_public(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    response = client.get(f"{MEMOS_URL}/{memo_id}/record")

    assert response.status_code == 401


def test_an_invalid_id_is_rejected(client, brand):
    assert (
        client.get(f"{MEMOS_URL}/not-an-id/record", headers=brand.headers).status_code
        == 422
    )


def test_it_is_rate_limited(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    url = f"{MEMOS_URL}/{memo_id}/record"
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(url, headers=brand.headers).status_code == 200

    response = client.get(url, headers=brand.headers)

    assert response.status_code == 429


# --- in the data export ------------------------------------------------------------


def test_both_parties_export_the_record_with_its_seals(client, brand, creator):
    memo_id = paid_deal(client, brand, creator)
    sealed = record_of(client, brand, memo_id)["entries"]

    for party in (brand, creator):
        exported = client.get("/api/v1/me/export", headers=party.headers).json()
        rows = exported["data"]["deal_record"]
        assert [r["seal"] for r in rows] == [e["seal"] for e in sealed]
        assert [r["previous_seal"] for r in rows] == [e["previous_seal"] for e in sealed]
        assert [r["kind"] for r in rows] == [e["kind"] for e in sealed]


def test_the_export_never_carries_the_other_sides_account_id(client, brand, creator):
    paid_deal(client, brand, creator)

    text = client.get("/api/v1/me/export", headers=creator.headers).text

    assert str(brand.account_id) not in text


def test_the_script_in_the_verification_guide_works(
    client, brand, creator, tmp_path, monkeypatch, capsys
):
    """Run the guide's own script, as a reader would, so the page can never
    drift from what the service does."""
    memo_id = paid_deal(client, brand, creator)
    record = record_of(client, creator, memo_id)
    (tmp_path / "record.json").write_text(json.dumps(record), encoding="utf-8")
    guide = (Path(__file__).parents[3] / "docs" / "DEAL_RECORD_VERIFY.md").read_text(
        encoding="utf-8"
    )
    script = next(
        block.split("\n", 1)[1]
        for block in guide.split("```")
        if block.startswith("python") and "record.json" in block
    )
    monkeypatch.chdir(tmp_path)

    exec(compile(script, "DEAL_RECORD_VERIFY.md", "exec"), {})  # noqa: S102

    assert capsys.readouterr().out.strip() == (
        f"Every seal matches. Latest seal: {record['latest_seal']}"
    )
