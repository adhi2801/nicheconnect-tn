"""A decline's date, the creator's change request, and the brand's first answer
(items 24, 25 and 28, D-089)."""

from datetime import timedelta

import pytest

from tests.deal_flow import (
    AGREED_DUE_ON,
    CAMPAIGNS_URL,
    MEMOS_URL,
    User,
    brand_user,
    creator_user,
)
from tests.modules.campaigns.test_campaign_summary_api import apply, open_campaign
from tests.modules.campaigns.test_invitation_api import creator_id_of, invite
from tests.step_up import download_export

APPLICATIONS_URL = "/api/v1/applications"
EXPORT_URL = "/api/v1/me/export"
ASKED = "Can we make it 2 reels instead of 3, for the same fee?"


def ts(clock) -> str:
    return clock.now.isoformat().replace("+00:00", "Z")


def memo_of(client, user: User, memo_id: str) -> dict:
    response = client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def application_of(client, user: User, application_id: str) -> dict:
    response = client.get(f"{APPLICATIONS_URL}/{application_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def move(client, user: User, application_id: str, action: str, **body) -> None:
    response = client.post(
        f"{APPLICATIONS_URL}/{application_id}/{action}",
        json=body or None,
        headers=user.headers,
    )
    assert response.status_code == 200, response.text


def request_change(client, creator: User, memo_id: str, message: str):
    return client.post(
        f"{MEMOS_URL}/{memo_id}/request-change",
        json={"message": message},
        headers=creator.headers,
    )


@pytest.fixture
def sent(client, db, clock):
    """A memo sent to the creator, waiting for an answer."""
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    application_id = apply(client, campaign_id, creator)
    move(client, brand, application_id, "shortlist")
    move(client, brand, application_id, "accept")
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "3 Instagram reels.",
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    return {"brand": brand, "creator": creator, "memo_id": memo_id}


# --- item 24: when a memo was declined ---------------------------------------------------


def test_a_decline_is_dated_when_it_happens(client, clock, sent):
    clock.advance(timedelta(hours=5))
    response = client.post(
        f"{MEMOS_URL}/{sent['memo_id']}/decline", headers=sent["creator"].headers
    )
    assert response.status_code == 200, response.text

    memo = memo_of(client, sent["brand"], sent["memo_id"])

    assert memo["status"] == "declined"
    assert memo["declined_at"] == ts(clock)


def test_a_memo_that_was_not_declined_has_no_decline_date(client, sent):
    client.post(f"{MEMOS_URL}/{sent['memo_id']}/accept", headers=sent["creator"].headers)

    assert memo_of(client, sent["brand"], sent["memo_id"])["declined_at"] is None


# --- item 25: what the creator asked to change -------------------------------------------


def test_the_brand_sees_what_the_creator_asked_to_change(client, sent):
    response = request_change(client, sent["creator"], sent["memo_id"], f"  {ASKED}  ")
    assert response.status_code == 200, response.text

    memo = memo_of(client, sent["brand"], sent["memo_id"])

    assert memo["status"] == "change_requested"
    assert memo["change_request_message"] == ASKED  # trimmed


def test_the_request_is_kept_after_the_memo_is_sent_again(client, sent):
    request_change(client, sent["creator"], sent["memo_id"], ASKED)
    client.patch(
        f"{MEMOS_URL}/{sent['memo_id']}",
        json={"deliverables": "2 Instagram reels."},
        headers=sent["brand"].headers,
    )
    client.post(f"{MEMOS_URL}/{sent['memo_id']}/send", headers=sent["brand"].headers)

    memo = memo_of(client, sent["creator"], sent["memo_id"])

    assert memo["status"] == "sent"
    assert memo["change_request_message"] == ASKED


def test_a_second_request_replaces_the_first(client, sent):
    request_change(client, sent["creator"], sent["memo_id"], ASKED)
    client.post(f"{MEMOS_URL}/{sent['memo_id']}/send", headers=sent["brand"].headers)
    second = "Please move the due date to the 20th."

    request_change(client, sent["creator"], sent["memo_id"], second)

    memo = memo_of(client, sent["brand"], sent["memo_id"])
    assert (memo["change_request_message"], memo["revision_count"]) == (second, 2)


def test_a_memo_never_sent_back_has_no_request(client, sent):
    assert (
        memo_of(client, sent["brand"], sent["memo_id"])["change_request_message"] is None
    )


def test_a_request_naming_a_price_or_a_number_raises_no_flag(client, sent):
    """Creator to brand, after they were matched: neither flag applies."""
    request_change(
        client,
        sent["creator"],
        sent["memo_id"],
        "Can we make it Rs 12,000? Call me on +91 98765 43210 to talk it through.",
    )

    assert memo_of(client, sent["brand"], sent["memo_id"])["text_flags"] == []


@pytest.mark.parametrize("message", ["", "   ", "abcd", "x" * 1001])
def test_a_request_outside_5_to_1000_characters_is_refused(client, sent, message):
    response = request_change(client, sent["creator"], sent["memo_id"], message)

    assert response.status_code == 422


def test_both_new_memo_fields_are_in_the_creators_export(client, clock, sent):
    request_change(client, sent["creator"], sent["memo_id"], ASKED)

    export = download_export(client, sent["creator"].headers).json()

    (memo,) = [m for m in export["data"]["deal_memos"] if m["id"] == sent["memo_id"]]
    assert memo["change_request_message"] == ASKED
    assert memo["declined_at"] is None


# --- item 28: when the brand first answered ----------------------------------------------


@pytest.fixture
def applied(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    return {
        "brand": brand,
        "creator": creator,
        "application_id": apply(client, campaign_id, creator),
        "campaign_id": campaign_id,
    }


def test_a_waiting_application_has_no_answer_yet(client, applied):
    found = application_of(client, applied["brand"], applied["application_id"])

    assert found["first_answered_at"] is None


def test_the_first_answer_is_kept_and_a_later_one_does_not_move_it(
    client, clock, applied
):
    clock.advance(timedelta(hours=3))
    move(client, applied["brand"], applied["application_id"], "shortlist")
    first = ts(clock)
    clock.advance(timedelta(days=2))
    move(client, applied["brand"], applied["application_id"], "accept")

    found = application_of(client, applied["creator"], applied["application_id"])

    assert found["status"] == "accepted"
    assert found["first_answered_at"] == first


def test_a_rejection_is_an_answer(client, clock, applied):
    clock.advance(timedelta(hours=1))
    move(
        client,
        applied["brand"],
        applied["application_id"],
        "reject",
        reason="budget_mismatch",
    )

    found = application_of(client, applied["brand"], applied["application_id"])

    assert found["first_answered_at"] == ts(clock)


def test_a_creator_withdrawing_is_not_the_brand_answering(client, applied):
    move(client, applied["creator"], applied["application_id"], "withdraw")

    found = application_of(client, applied["creator"], applied["application_id"])

    assert found["first_answered_at"] is None


def test_an_invitation_has_no_first_answer_from_the_brand(client, db, clock):
    """The brand asked first; the creator's reply is not the brand's answer."""
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    response = invite(
        client, brand, campaign_id, creator_id_of(db, creator), note="Join us."
    )
    assert response.status_code == 201, response.text
    invitation_id = response.json()["id"]
    move(client, brand, invitation_id, "withdraw-invitation")

    assert application_of(client, brand, invitation_id)["first_answered_at"] is None


def test_the_first_answer_is_in_the_export(client, clock, applied):
    move(client, applied["brand"], applied["application_id"], "shortlist")

    sent = download_export(client, applied["creator"].headers).json()["data"][
        "applications_sent"
    ]

    (found,) = [a for a in sent if a["id"] == applied["application_id"]]
    assert found["first_answered_at"] == ts(clock)


def test_the_campaigns_application_list_carries_it(client, applied):
    move(client, applied["brand"], applied["application_id"], "shortlist")

    items = client.get(
        f"{CAMPAIGNS_URL}/{applied['campaign_id']}/applications",
        headers=applied["brand"].headers,
    ).json()["items"]

    assert items[0]["first_answered_at"] is not None
