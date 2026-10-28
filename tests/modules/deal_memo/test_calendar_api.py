"""A deal's agreed dates as a calendar file, over HTTP (item 69, D-102)."""

import uuid
from datetime import UTC

import pytest
from sqlalchemy import select, text

from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.proof_service import approval_deadline
from app.modules.payment_status.models import PaymentStatus
from tests.deal_flow import LINK, MEMOS_URL, accepted_memo, brand_user, creator_user
from tests.query_counts import queries_for

PROOF = {"content_url": LINK, "format": "reel", "disclosure_confirmed": True}


def url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/calendar.ics"


def lines(response) -> list[str]:
    return response.text.replace("\r\n ", "").split("\r\n")


@pytest.fixture
def deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    return {
        "memo_id": accepted_memo(client, brand, creator),
        "brand": brand,
        "creator": creator,
    }


def test_an_accepted_deal_s_content_date_is_in_the_file(client, deal):
    response = client.get(url(deal["memo_id"]), headers=deal["creator"].headers)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="deal-{deal["memo_id"]}.ics"'
    )
    assert response.headers["cache-control"] == "private, no-store"
    got = lines(response)
    assert "DTSTART;VALUE=DATE:20261231" in got
    assert "SUMMARY:Content due: Pongal sweets launch" in got
    assert f"UID:deal-{deal['memo_id']}-content-due@nicheconnect-tn" in got
    assert (
        "NicheConnect never asks anyone to pay to get a deal."
        in response.text.replace("\r\n ", "")
    )


def test_both_sides_get_the_same_events(client, deal):
    def events(user):
        return [
            line
            for line in lines(client.get(url(deal["memo_id"]), headers=user.headers))
            if not line.startswith("DTSTAMP")
        ]

    assert events(deal["brand"]) == events(deal["creator"])


def test_waiting_proof_adds_the_moment_it_approves_itself(client, db, deal):
    client.post(
        f"{MEMOS_URL}/{deal['memo_id']}/proof",
        json=PROOF,
        headers=deal["creator"].headers,
    )
    memo = db.get(DealMemo, uuid.UUID(deal["memo_id"]))
    proof = db.scalar(
        select(DeliverableProof).where(DeliverableProof.deal_memo_id == memo.id)
    )
    moment = approval_deadline(memo, proof, [proof]).astimezone(UTC)

    got = lines(client.get(url(deal["memo_id"]), headers=deal["brand"].headers))

    assert "SUMMARY:Proof approves itself: Pongal sweets launch" in got
    # Midnight in Tamil Nadu, written in UTC: 18:30 the evening before.
    assert f"DTSTART:{moment:%Y%m%dT%H%M%SZ}" in got
    assert moment.strftime("%H%M") == "1830"


def test_an_open_payment_adds_its_due_date_and_a_confirmed_one_removes_it(
    client, db, deal
):
    memo_id, brand, creator = deal["memo_id"], deal["brand"], deal["creator"]
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    payment = db.scalar(
        select(PaymentStatus).where(PaymentStatus.deal_memo_id == uuid.UUID(memo_id))
    )

    got = lines(client.get(url(memo_id), headers=creator.headers))
    assert f"DTSTART;VALUE=DATE:{payment.due_on:%Y%m%d}" in got
    assert "SUMMARY:Payment due: Pongal sweets launch" in got
    assert not any(line.startswith("SUMMARY:Proof approves itself") for line in got)

    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678901"},
        headers=brand.headers,
    )
    confirmed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    got = lines(client.get(url(memo_id), headers=creator.headers))
    assert not any(line.startswith("SUMMARY:Payment due") for line in got)


def test_a_memo_not_yet_accepted_has_no_dates(client, db, deal):
    memo = db.get(DealMemo, uuid.UUID(deal["memo_id"]))
    memo.status, memo.accepted_at = "sent", None
    db.flush()

    got = lines(client.get(url(deal["memo_id"]), headers=deal["brand"].headers))

    assert "BEGIN:VCALENDAR" in got and "BEGIN:VEVENT" not in got


def test_a_title_cannot_add_lines_to_the_file(client, db, deal):
    db.execute(
        text(
            "UPDATE campaign SET title = 'Sweets; launch, 2026\nEND:VEVENT' WHERE id ="
            " (SELECT campaign_id FROM application a JOIN deal_memo m ON m.application_id = a.id"
            " WHERE m.id = :m)"
        ),
        {"m": deal["memo_id"]},
    )

    got = lines(client.get(url(deal["memo_id"]), headers=deal["brand"].headers))

    assert "SUMMARY:Content due: Sweets\\; launch\\, 2026\\nEND:VEVENT" in got
    assert got.count("END:VEVENT") == 1


def test_it_needs_a_login(client, deal):
    assert client.get(url(deal["memo_id"])).status_code == 401


def test_a_stranger_gets_not_found(client, db, clock, deal):
    assert (
        client.get(
            url(deal["memo_id"]), headers=brand_user(db, clock).headers
        ).status_code
        == 404
    )


def test_the_same_queries_however_long_the_history(client, deal):
    memo_id, brand, creator = deal["memo_id"], deal["brand"], deal["creator"]

    def resubmit() -> None:
        """A proof sent, then sent back for changes."""
        proof_id = client.post(
            f"{MEMOS_URL}/{memo_id}/proof", json=PROOF, headers=creator.headers
        ).json()["id"]
        client.post(
            f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
            json={"note": "Please add the product name."},
            headers=brand.headers,
        )

    none_yet = queries_for(client, url(memo_id), creator.headers)
    resubmit()
    once = queries_for(client, url(memo_id), creator.headers)
    for _ in range(3):
        resubmit()

    assert queries_for(client, url(memo_id), creator.headers) == once == none_yet
