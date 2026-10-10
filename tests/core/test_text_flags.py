"""Warnings on free text (item 60): real wording that must flag, and must not.

The examples are the shapes reported in Indian creator scams (fake brands
asking for registration or shipping fees) and the ordinary business wording
that sits right next to them. A false positive found later becomes a case
here.
"""

import pytest

from app.core.text_flags import flags_in


def money(text: str) -> bool:
    return "asks_for_money" in flags_in(text, money=True, contact=False)


@pytest.mark.parametrize(
    "text",
    [
        "Pay a registration fee of ₹2,000 to confirm your collaboration slot.",
        "A refundable security deposit of Rs 1500 is required.",
        "Processing fee ₹499 applies before we ship the products.",
        "Kindly pay the shipping charges and we will dispatch the hamper.",
        "Courier charges of ₹750 to be paid by the creator.",
        "Please pay first, the amount is refunded after the post goes live.",
        "Send ₹1,000 to this UPI to lock your spot.",
        "pay rs 999 to register for the campaign",
        "Verification fee: INR 300",
        "Joining fees are refundable once you complete 3 posts.",
    ],
)
def test_a_request_for_money_is_flagged(text):
    assert money(text)


@pytest.mark.parametrize(
    "text",
    [
        "We pay ₹5,000 per reel, within 7 days of approval.",
        "Budget: Rs 8,000 to Rs 15,000 depending on reach.",
        "We cover the shipping charges for the sample box.",
        "Fee: ₹12,000 for 3 reels and 2 stories.",
        "Payment by UPI after the content is approved.",
        "Free delivery of the product to your address in Coimbatore.",
        "Our registration with FSSAI is attached for reference.",
        "",
    ],
)
def test_ordinary_business_wording_is_not(text):
    assert not money(text)


@pytest.mark.parametrize(
    ("text", "flag"),
    [
        ("Call me on 98765 43210 to discuss", "phone_number"),
        ("My number is +91-9876543210", "phone_number"),
        ("reach me at 919876543210", "phone_number"),
        ("Mail priya.eats@gmail.com", "email"),
        ("Send it to meena.cooks@okhdfcbank", "upi_id"),
        ("ping wa.me/919876543210", "messaging_link"),
        ("Join https://t.me/ammasweets_collabs", "messaging_link"),
        ("WhatsApp me for details", "messaging_link"),
    ],
)
def test_contact_details_are_flagged_before_a_deal(text, flag):
    assert flag in flags_in(text, money=False, contact=True)


@pytest.mark.parametrize(
    "text",
    [
        "I have 12,000 followers and 4.2% engagement.",
        "Posted 3 reels in September 2026, reach 45,000.",
        "Order 12345678 shipped.",
        "Tracking number 4419876543210 from the courier.",
        "Invoice 98765432101 attached.",
        "Find our menu at ammasweets.in",
    ],
)
def test_numbers_that_are_not_phones_are_not_flagged(text):
    assert flags_in(text, money=False, contact=True) == []


def test_an_email_is_not_also_a_upi_id():
    assert flags_in("priya@example.com", money=False, contact=True) == ["email"]


def test_nothing_is_flagged_when_neither_check_applies():
    text = "Pay ₹2,000 registration fee. Call 9876543210."

    assert flags_in(text, money=False, contact=False) == []


def test_flags_come_in_a_fixed_order():
    text = "Registration fee ₹500, WhatsApp me on 9876543210 or mail a@b.in"

    assert flags_in(text, money=True, contact=True) == [
        "asks_for_money",
        "phone_number",
        "email",
        "messaging_link",
    ]
