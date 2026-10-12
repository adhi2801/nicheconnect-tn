"""A campaign report a brand can hand to its boss (item 47, D-088)."""

import csv
import io
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.clock import india_date
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application
from app.modules.campaigns.report_csv import COLUMNS
from app.modules.deal_memo import proof_reader, record_service
from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from app.modules.deal_memo.anchor_service import covers_until
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof, ProofFile
from app.modules.deal_memo.proof_reading_models import ProofFileReading
from app.modules.deal_memo.proof_service import approval_deadline
from app.modules.deal_memo.record_service import Verification
from app.modules.payment_status.models import PaymentStatus
from tests.deal_flow import (
    AGREED_DUE_ON,
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    User,
    brand_user,
    creator_user,
)
from tests.factories import FIXED_NOW, build_creator
from tests.modules.campaigns.test_campaign_summary_api import (
    RRN,
    agree,
    apply,
    finish,
    open_campaign,
)
from tests.query_counts import queries_for

TODAY = india_date(FIXED_NOW).isoformat()


def report_url(campaign_id: str) -> str:
    return f"{CAMPAIGNS_URL}/{campaign_id}/report"


def csv_url(campaign_id: str) -> str:
    return f"{CAMPAIGNS_URL}/{campaign_id}/report.csv"


def report(client: TestClient, brand: User, campaign_id: str) -> dict:
    response = client.get(report_url(campaign_id), headers=brand.headers)
    assert response.status_code == 200, response.text
    return response.json()


def rows(client: TestClient, brand: User, campaign_id: str) -> list[dict[str, str]]:
    response = client.get(csv_url(campaign_id), headers=brand.headers)
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.text.removeprefix("﻿"))))


def deal(body: dict, memo_id: str) -> dict:
    return next(line for line in body["deals"] if line["deal_memo_id"] == memo_id)


def submit(client: TestClient, creator: User, memo_id: str) -> str:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def approve(client: TestClient, brand: User, memo_id: str, proof_id: str) -> None:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert response.status_code == 200, response.text


def memo_for(
    client: TestClient, brand: User, application_id: str, send: bool = True
) -> str:
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 Instagram reels.",
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    ).json()["id"]
    if send:
        client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    return memo_id


@pytest.fixture
def board(client, db, clock):
    """One deal finished, one at payment, one memo unanswered, one draft, one
    applicant turned down."""
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    done, paying, asked, drafted, turned_down = (
        creator_user(db, clock) for _ in range(5)
    )
    finished_memo = agree(client, brand, done, apply(client, campaign_id, done))
    finish(client, brand, done, finished_memo)
    paying_memo = agree(client, brand, paying, apply(client, campaign_id, paying))
    approve(client, brand, paying_memo, submit(client, paying, paying_memo))
    sent_memo = memo_for(client, brand, apply(client, campaign_id, asked))
    draft_memo = memo_for(client, brand, apply(client, campaign_id, drafted), send=False)
    rejected = apply(client, campaign_id, turned_down)
    client.post(
        f"/api/v1/applications/{rejected}/reject",
        json={"reason": "budget_mismatch"},
        headers=brand.headers,
    )
    return {
        "brand": brand,
        "campaign_id": campaign_id,
        "done": done,
        "finished_memo": finished_memo,
        "paying_memo": paying_memo,
        "sent_memo": sent_memo,
        "draft_memo": draft_memo,
    }


# --- the deals ---------------------------------------------------------------------------


def test_every_deal_is_listed_where_it_stands_and_a_draft_is_not(client, board):
    body = report(client, board["brand"], board["campaign_id"])

    stages = {line["deal_memo_id"]: line["stage"] for line in body["deals"]}
    assert stages == {
        board["finished_memo"]: "finished",
        board["paying_memo"]: "payment",
        board["sent_memo"]: "memo_sent",
    }
    assert body["campaign_id"] == board["campaign_id"]
    assert (body["status"], body["campaign_type"]) == ("open", "paid")


def test_a_finished_deal_shows_its_delivery_approval_and_payment(client, board):
    line = deal(
        report(client, board["brand"], board["campaign_id"]), board["finished_memo"]
    )

    assert line["creator"]["display_name"] == "Priya Eats"
    assert line["creator"]["handle"].startswith("proof")
    assert (line["fee_amount_paise"], line["currency"]) == (800_000, "INR")
    assert line["first_submitted_on"] == TODAY
    assert line["delivered_on_time"] is True
    assert (line["approved_on"], line["approved_by_clock"]) == (TODAY, False)
    assert (line["content_url"], line["disclosure_confirmed"]) == (LINK, True)
    assert line["payment_state"] == "confirmed"
    assert line["payment_marked_paid_on"] == line["payment_confirmed_on"] == TODAY
    assert line["paid_on_time"] is True


def test_an_unanswered_memo_has_nothing_delivered_or_paid_yet(client, board):
    line = deal(report(client, board["brand"], board["campaign_id"]), board["sent_memo"])

    assert line["waiting_on"] == "creator"
    for field in (
        "first_submitted_on",
        "delivered_on_time",
        "approved_on",
        "content_url",
        "payment_state",
        "paid_on_time",
    ):
        assert line[field] is None, field


def test_the_creator_is_shown_by_name_and_handle_only(client, board):
    """Nothing private: no phone, no UPI ID, no payment reference."""
    response = client.get(
        report_url(board["campaign_id"]), headers=board["brand"].headers
    )

    assert set(response.json()["deals"][0]["creator"]) == {"display_name", "handle"}
    assert RRN not in response.text


def test_only_this_campaigns_deals_are_in_it(client, db, clock, board):
    """Two campaigns of one brand, so a missing campaign filter cannot pass."""
    other = open_campaign(client, board["brand"])
    lone = creator_user(db, clock)
    other_memo = agree(client, board["brand"], lone, apply(client, other, lone))

    ids = {
        line["deal_memo_id"]
        for line in report(client, board["brand"], board["campaign_id"])["deals"]
    }

    assert other_memo not in ids
    assert len(ids) == 3


def test_a_campaign_with_no_deals_reports_zeros_and_nulls(client, db, clock):
    brand = brand_user(db, clock)
    body = report(client, brand, open_campaign(client, brand))

    assert body["deals"] == []
    totals = body["totals"]
    assert (totals["deals"], totals["agreed_value_paise"]) == (0, 0)
    assert set(totals["results"]["numbers"].values()) == {None}
    assert totals["records_intact"] is True


# --- the totals --------------------------------------------------------------------------


def test_the_totals_count_agreed_deals_and_money_by_who_said_what(client, board):
    totals = report(client, board["brand"], board["campaign_id"])["totals"]

    assert totals["applications"]["accepted"] == 4
    assert totals["applications"]["rejected"] == 1
    assert (totals["deals"], totals["deals_agreed"], totals["deals_finished"]) == (
        3,
        2,
        1,
    )
    # The unanswered memo's fee is not agreed value.
    assert totals["agreed_value_paise"] == 1_600_000
    assert totals["marked_paid_paise"] == totals["confirmed_paise"] == 800_000
    assert (totals["deliveries_judged"], totals["delivered_on_time"]) == (2, 2)
    assert (totals["payments_sent"], totals["payments_sent_on_time"]) == (1, 1)
    assert totals["records_intact"] is True


def test_money_said_to_be_sent_is_not_counted_as_confirmed(client, board):
    brand = board["brand"]
    client.post(
        f"{MEMOS_URL}/{board['paying_memo']}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678902"},
        headers=brand.headers,
    )

    totals = report(client, brand, board["campaign_id"])["totals"]

    assert totals["marked_paid_paise"] == 1_600_000
    assert totals["confirmed_paise"] == 800_000


def test_a_barter_deal_is_counted_as_barter_with_no_value(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Café opening",
            "description": "Come to our opening and post about the food.",
            "campaign_type": "barter",
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "1 Instagram reel",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    creator = creator_user(db, clock)
    application_id = apply(client, campaign_id, creator)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "1 reel at the opening.", "content_due_on": AGREED_DUE_ON},
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    assert (
        client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers).status_code
        == 200
    )

    body = report(client, brand, campaign_id)

    assert body["totals"]["barter_deals_agreed"] == 1
    assert body["totals"]["agreed_value_paise"] == 0
    assert body["deals"][0]["fee_amount_paise"] is None


# --- dates and the clock -----------------------------------------------------------------


def late_campaign(client, db, clock):
    """A deal due in three days whose work arrives a week later."""
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    creator = creator_user(db, clock)
    due_on = (india_date(clock.now) + timedelta(days=3)).isoformat()
    application_id = apply(client, campaign_id, creator)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 Instagram reels.",
            "fee_amount_paise": 800_000,
            "content_due_on": due_on,
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)
    clock.advance(timedelta(days=7))
    proof_id = submit(client, creator, memo_id)
    return brand, campaign_id, memo_id, proof_id


def test_work_sent_after_the_agreed_date_is_late(client, db, clock):
    brand, campaign_id, memo_id, _ = late_campaign(client, db, clock)

    line = deal(report(client, brand, campaign_id), memo_id)

    assert line["delivered_on_time"] is False
    assert report(client, brand, campaign_id)["totals"]["delivered_on_time"] == 0


def test_work_nobody_reviewed_is_approved_by_the_clock_on_its_deadline(client, db, clock):
    brand, campaign_id, memo_id, proof_id = late_campaign(client, db, clock)
    memo = db.get(DealMemo, uuid.UUID(memo_id))
    proof = db.get(DeliverableProof, uuid.UUID(proof_id))
    deadline = approval_deadline(memo, proof, [proof])
    clock.advance(timedelta(days=10))  # past the 7-day window, before payment is due

    line = deal(report(client, brand, campaign_id), memo_id)

    assert line["approved_by_clock"] is True
    assert line["approved_on"] == india_date(deadline).isoformat()
    assert line["stage"] == "payment"
    # Not yet written down, so worked out as it will be (open_on_approval).
    due_on = india_date(deadline) + timedelta(days=memo.payment_due_days)
    assert (line["payment_state"], line["payment_due_on"]) == ("due", due_on.isoformat())
    assert (
        db.scalar(select(PaymentStatus.id).where(PaymentStatus.deal_memo_id == memo.id))
        is None
    )


def test_money_marked_sent_after_its_due_date_was_not_on_time(client, db, clock, board):
    brand = board["brand"]
    clock.advance(timedelta(days=30))
    client.post(
        f"{MEMOS_URL}/{board['paying_memo']}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678903"},
        headers=brand.headers,
    )

    body = report(client, brand, board["campaign_id"])

    assert deal(body, board["paying_memo"])["paid_on_time"] is False
    assert (body["totals"]["payments_sent"], body["totals"]["payments_sent_on_time"]) == (
        2,
        1,
    )


# --- results from screenshots ------------------------------------------------------------


def add_reading(db, memo_id: str, proof_id: uuid.UUID, **numbers) -> ProofFileReading:
    sha = uuid.uuid4().hex * 2
    file = ProofFile(
        deal_memo_id=uuid.UUID(memo_id),
        uploader_account_id=_creator_account(db, memo_id),
        storage_key=f"proof-files/incoming/{uuid.uuid4()}",
        content_type="image/png",
        size_bytes=1024,
        sha256=sha,
        status="cleaned",
        proof_id=proof_id,
        # The next free place on this proof: each file has its own.
        position=db.scalar(
            select(func.count())
            .select_from(ProofFile)
            .where(ProofFile.proof_id == proof_id)
        ),
        attached_at=FIXED_NOW,
        clean_key=f"proof-files/clean/{uuid.uuid4()}.png",
        clean_sha256=sha,
        clean_size_bytes=900,
        cleaned_at=FIXED_NOW,
    )
    db.add(file)
    db.flush()
    fields = {
        "proof_file_id": file.id,
        "status": "read",
        "model": "claude-opus-5-5",
        "prompt_version": proof_reader.PROMPT_VERSION,
        "read_at": FIXED_NOW,
    }
    fields.update(numbers)
    reading = ProofFileReading(**fields)
    db.add(reading)
    db.flush()
    return reading


def _creator_account(db, memo_id: str) -> uuid.UUID:
    return db.scalar(
        select(Creator.account_id)
        .join(Application, Application.creator_id == Creator.id)
        .join(DealMemo, DealMemo.application_id == Application.id)
        .where(DealMemo.id == uuid.UUID(memo_id))
    )


def proofs_of(db, memo_id: str) -> list[DeliverableProof]:
    return list(
        db.scalars(
            select(DeliverableProof)
            .where(DeliverableProof.deal_memo_id == uuid.UUID(memo_id))
            .order_by(DeliverableProof.created_at)
        )
    )


def test_results_sum_the_approved_works_readings_and_set_aside_the_disputed(
    client, db, board
):
    approved = proofs_of(db, board["finished_memo"])[-1]
    add_reading(db, board["finished_memo"], approved.id, views=1_000, reach=800)
    add_reading(db, board["finished_memo"], approved.id, views=500, abbreviated=["views"])
    add_reading(
        db,
        board["finished_memo"],
        approved.id,
        views=99_999,
        creator_marked_at=FIXED_NOW,
        creator_note="Views are 9,999, not 99,999.",
    )
    add_reading(
        db, board["finished_memo"], approved.id, status="failed", failure="api_error"
    )

    body = report(client, board["brand"], board["campaign_id"])

    results = deal(body, board["finished_memo"])["results"]
    assert results["source"] == "read_from_screenshots"
    assert (results["readings"], results["readings_marked_wrong"]) == (2, 1)
    assert results["includes_abbreviated"] is True
    assert (results["numbers"]["views"], results["numbers"]["reach"]) == (1_500, 800)
    assert results["numbers"]["likes"] is None
    assert body["totals"]["results"]["numbers"]["views"] == 1_500


def test_readings_of_work_sent_back_are_not_results(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    creator = creator_user(db, clock)
    memo_id = agree(client, brand, creator, apply(client, campaign_id, creator))
    first = submit(client, creator, memo_id)
    client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{first}/request-revision",
        json={"note": "The ad label is missing from the caption."},
        headers=brand.headers,
    )
    add_reading(db, memo_id, uuid.UUID(first), views=7_000)
    second = submit(client, creator, memo_id)
    approve(client, brand, memo_id, second)
    add_reading(db, memo_id, uuid.UUID(second), views=300)

    results = deal(report(client, brand, campaign_id), memo_id)["results"]

    assert (results["readings"], results["numbers"]["views"]) == (1, 300)


def test_work_sent_back_and_not_yet_approved_has_no_results(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    creator = creator_user(db, clock)
    memo_id = agree(client, brand, creator, apply(client, campaign_id, creator))
    proof_id = submit(client, creator, memo_id)
    client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
        json={"note": "The ad label is missing from the caption."},
        headers=brand.headers,
    )
    add_reading(db, memo_id, uuid.UUID(proof_id), views=7_000)

    line = deal(report(client, brand, campaign_id), memo_id)

    assert (line["approved_on"], line["content_url"]) == (None, None)
    assert line["results"]["readings"] == 0
    assert line["results"]["numbers"]["views"] is None


def test_totals_add_up_the_results_of_every_deal(client, db, board):
    for memo_id, views in ((board["finished_memo"], 1_000), (board["paying_memo"], 250)):
        add_reading(db, memo_id, proofs_of(db, memo_id)[-1].id, views=views, likes=10)

    totals = report(client, board["brand"], board["campaign_id"])["totals"]["results"]

    assert totals["numbers"]["views"] == 1_250
    assert totals["numbers"]["likes"] == 20
    assert totals["readings"] == 2


# --- the deal record ---------------------------------------------------------------------


def test_each_deal_carries_its_records_latest_seal(client, board):
    brand = board["brand"]
    record = client.get(
        f"{MEMOS_URL}/{board['finished_memo']}/record", headers=brand.headers
    ).json()

    seal = deal(report(client, brand, board["campaign_id"]), board["finished_memo"])[
        "record"
    ]

    assert seal["latest_seal"] == record["latest_seal"]
    assert seal["entries"] == len(record["entries"])
    assert seal["intact"] is True
    assert seal["stamped_on"] is None  # no checkpoint stamped yet


def checkpoint(db, day: date, stamped: bool) -> None:
    row = DealRecordCheckpoint(
        covers_until=covers_until(day), leaf_count=1, merkle_root=b"\x00" * 32
    )
    db.add(row)
    db.flush()
    if stamped:
        db.add(
            DealRecordTimestamp(
                checkpoint_id=row.id,
                authority="digicert",
                token=b"\x30\x03\x02\x01\x00",
                signed_at=covers_until(day) + timedelta(minutes=5),
            )
        )
        db.flush()


def test_the_seal_is_dated_by_the_first_stamped_checkpoint_after_it(client, db, board):
    today = india_date(FIXED_NOW)
    checkpoint(db, today, stamped=True)  # cut off before the deal began
    checkpoint(db, today + timedelta(days=1), stamped=False)  # not stamped
    checkpoint(db, today + timedelta(days=2), stamped=True)
    checkpoint(db, today + timedelta(days=3), stamped=True)

    body = report(client, board["brand"], board["campaign_id"])

    expected = (today + timedelta(days=2)).isoformat()
    assert {line["record"]["stamped_on"] for line in body["deals"]} == {expected}


def test_a_record_that_does_not_check_is_reported(client, board, monkeypatch):
    """The record table refuses edits, so the check itself is made to fail.
    `test_deal_record_service.py` proves the check catches each kind of edit."""
    broken = board["paying_memo"]
    real = record_service.verify

    def verify(memo, entries):
        if str(memo.id) == broken:
            return Verification(False, 1, None)
        return real(memo, entries)

    monkeypatch.setattr(record_service, "verify", verify)

    body = report(client, board["brand"], board["campaign_id"])

    assert deal(body, broken)["record"]["intact"] is False
    assert deal(body, board["finished_memo"])["record"]["intact"] is True
    assert body["totals"]["records_intact"] is False


# --- the spreadsheet ---------------------------------------------------------------------


def test_the_spreadsheet_downloads_as_a_file_never_cached(client, board):
    response = client.get(csv_url(board["campaign_id"]), headers=board["brand"].headers)

    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    disposition = response.headers["content-disposition"]
    short = uuid.UUID(board["campaign_id"]).hex[:8]
    assert disposition == (f'attachment; filename="campaign-report-{short}-{TODAY}.csv"')


def test_the_spreadsheet_opens_in_excel_as_utf8_with_crlf_lines(client, board):
    raw = client.get(
        csv_url(board["campaign_id"]), headers=board["brand"].headers
    ).content

    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\r\n") == 4  # the header and three deals
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_the_spreadsheet_has_one_row_per_deal_in_the_reports_order(client, board):
    brand, campaign_id = board["brand"], board["campaign_id"]

    found = rows(client, brand, campaign_id)

    assert list(found[0]) == list(COLUMNS)
    assert [row["deal_memo_id"] for row in found] == [
        line["deal_memo_id"] for line in report(client, brand, campaign_id)["deals"]
    ]
    finished = next(row for row in found if row["deal_memo_id"] == board["finished_memo"])
    assert finished["fee_inr"] == "8000.00"
    assert finished["stage"] == "finished"
    assert finished["paid_on_time"] == "yes"
    assert finished["content_url"] == LINK
    assert finished["views"] == ""  # nothing read


def test_a_name_typed_as_a_formula_cannot_run_in_the_spreadsheet(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    sly = build_creator(
        db,
        handle=f"sly{uuid.uuid4().hex[:12]}",
        display_name='=HYPERLINK("https://evil.example","Paid")',
    )
    db.add(sly)
    db.flush()
    creator = User(sly.account_id, "creator", clock)
    agree(client, brand, creator, apply(client, campaign_id, creator))

    row = rows(client, brand, campaign_id)[0]

    assert row["creator"] == '\'=HYPERLINK("https://evil.example","Paid")'
    # The JSON is not a spreadsheet: it carries the name as typed.
    assert report(client, brand, campaign_id)["deals"][0]["creator"]["display_name"] == (
        '=HYPERLINK("https://evil.example","Paid")'
    )


def test_deliverables_with_commas_quotes_and_line_breaks_stay_in_one_cell(
    client, db, clock
):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    typed = '2 reels, 1 "story"\nposted by Friday'
    application_id = apply(client, campaign_id, creator_user(db, clock))
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": typed,
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)

    found = rows(client, brand, campaign_id)

    row = next(row for row in found if row["deal_memo_id"] == memo_id)
    assert row["deliverables"] == typed


# --- cost and access ---------------------------------------------------------------------


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_a_bigger_campaign_costs_no_more_queries(client, db, clock, board, url):
    brand = board["brand"]
    small = open_campaign(client, brand)
    lone = creator_user(db, clock)
    lone_memo = agree(client, brand, lone, apply(client, small, lone))
    finish(client, brand, lone, lone_memo)
    add_reading(db, lone_memo, proofs_of(db, lone_memo)[-1].id, views=10)
    for memo_id in (board["finished_memo"], board["paying_memo"]):
        add_reading(db, memo_id, proofs_of(db, memo_id)[-1].id, views=10)
    checkpoint(db, india_date(FIXED_NOW) + timedelta(days=1), stamped=True)

    one_deal = queries_for(client, url(small), brand.headers)
    three_deals = queries_for(client, url(board["campaign_id"]), brand.headers)

    assert three_deals == one_deal


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_another_brands_campaign_is_not_found(client, db, clock, board, url):
    stranger = brand_user(db, clock)

    response = client.get(url(board["campaign_id"]), headers=stranger.headers)

    assert response.status_code == 404


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_a_creator_cannot_read_a_campaign_report(client, board, url):
    response = client.get(url(board["campaign_id"]), headers=board["done"].headers)

    assert response.status_code == 403


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_it_needs_a_login(client, board, url):
    assert client.get(url(board["campaign_id"])).status_code == 401


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_an_unknown_campaign_is_not_found(client, db, clock, url):
    response = client.get(
        url("00000000-0000-4000-8000-000000000000"),
        headers=brand_user(db, clock).headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_a_malformed_id_is_refused(client, db, clock, url):
    response = client.get(url("not-a-uuid"), headers=brand_user(db, clock).headers)

    assert response.status_code == 422


def test_the_report_is_never_cached(client, board):
    response = client.get(
        report_url(board["campaign_id"]), headers=board["brand"].headers
    )

    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("url", [report_url, csv_url])
def test_reports_are_rate_limited(client, db, clock, url):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    for _ in range(20):
        assert client.get(url(campaign_id), headers=brand.headers).status_code == 200

    response = client.get(url(campaign_id), headers=brand.headers)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
