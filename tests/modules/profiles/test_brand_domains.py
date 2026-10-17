"""A brand's domain claim, as pure rules (item 74, D-106)."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.profiles import brand_domains as rules
from app.modules.profiles.brand_domain_models import (
    DOMAIN_PATTERN,
    MAX_ABSENT_CHECKS,
    TOKEN_LENGTH,
    TOKEN_PATTERN,
)
from app.modules.profiles.brand_domains import CheckOutcome, ResolverAnswer

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)

# --- which domains can be claimed ---------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "claimed"),
    [
        ("smallshop.in", "smallshop.in"),
        ("SmallShop.IN", "smallshop.in"),
        ("  smallshop.in  ", "smallshop.in"),
        ("smallshop.in.", "smallshop.in"),
        ("www.smallshop.in", "smallshop.in"),
        ("smallshop.co.in", "smallshop.co.in"),
        ("www.smallshop.co.in", "smallshop.co.in"),
        ("chennai-sweets.com", "chennai-sweets.com"),
        ("4u.in", "4u.in"),
    ],
)
def test_a_website_s_own_domain_is_accepted(typed, claimed):
    assert rules.registrable_domain(typed) == claimed


@pytest.mark.parametrize(
    ("typed", "says"),
    [
        # A name under the domain: the claim is to the domain itself.
        ("shop.smallshop.in", "Claim the domain itself, smallshop.in"),
        ("nykaa.com.evil.ru", "Claim the domain itself, evil.ru"),
        # Suffixes many sites share.
        ("co.in", "a suffix many sites share"),
        ("in", "a suffix many sites share"),
        ("myshopify.com", "a suffix many sites share"),
        ("github.io", "a suffix many sites share"),
        # Shapes a domain cannot have.
        ("", "Enter your website's domain"),
        ("https://smallshop.in", "Use only letters a to z"),
        ("smallshop.in/about", "Use only letters a to z"),
        ("small shop.in", "Use only letters a to z"),
        ("small_shop.in", "Use only letters a to z"),
        ("me@smallshop.in", "Use only letters a to z"),
        ("smallshop..in", "Use only letters a to z"),
        ("-smallshop.in", "cannot start or end with a hyphen"),
        ("smallshop-.in", "cannot start or end with a hyphen"),
        ("a" * 64 + ".in", "Use only letters a to z"),
        # Other scripts, as typed and as punycode.
        ("nykаa.com", "Use only letters a to z"),  # noqa: RUF001 - the look-alike letter is the point of the test
        ("xn--nyka-x2a.com", "Domains in other scripts cannot be claimed"),
        ("சென்னை.in", "Use only letters a to z"),
    ],
)
def test_anything_else_is_refused_saying_what_to_do(typed, says):
    with pytest.raises(rules.DomainNotAccepted, match=re.escape(says)):
        rules.registrable_domain(typed)


def test_a_domain_longer_than_dns_allows_is_refused():
    with pytest.raises(rules.DomainNotAccepted):
        rules.registrable_domain(("a" * 60 + ".") * 4 + "in")


def test_what_is_accepted_is_what_the_database_holds():
    assert re.fullmatch(DOMAIN_PATTERN, rules.registrable_domain("www.Small-Shop.co.in"))


# --- what the brand publishes -------------------------------------------------------------


def test_a_token_is_128_random_bits_the_database_accepts():
    first, second = rules.new_token(), rules.new_token()

    assert len(first) == TOKEN_LENGTH
    assert re.fullmatch(TOKEN_PATTERN, first)
    assert first != second


def test_the_record_sits_at_our_own_underscore_name():
    assert rules.record_name("smallshop.in") == "_nicheconnect-challenge.smallshop.in"
    assert rules.record_value("abc") == "nicheconnect-domain-verification=abc"


# --- what the resolvers said --------------------------------------------------------------

TOKEN = "mfrggzdfmztwq2lknnwg23tpoa"
RECORD = rules.record_value(TOKEN)


def answer(*values: str, authenticated: bool = True) -> ResolverAnswer:
    return ResolverAnswer(values=values, authenticated=authenticated)


FAILED = ResolverAnswer(values=None)


def test_found_when_both_resolvers_see_the_record():
    assert rules.classify([answer(RECORD), answer(RECORD)], TOKEN) == CheckOutcome(
        "found", dnssec_validated=True
    )


def test_found_among_other_records_at_the_name():
    """Several vendors may share a name: at least one record must match."""
    outcome = rules.classify(
        [answer("v=spf1 -all", RECORD), answer(RECORD, "other")], TOKEN
    )

    assert outcome.result == "found"


def test_dnssec_counts_only_when_both_validated():
    outcome = rules.classify([answer(RECORD), answer(RECORD, authenticated=False)], TOKEN)

    assert outcome == CheckOutcome("found", dnssec_validated=False)


@pytest.mark.parametrize(
    "answers",
    [
        [answer(), answer()],
        [answer(RECORD), answer()],
        [answer(), answer(RECORD)],
        [answer("nicheconnect-domain-verification=someoneelse"), answer()],
        # Someone else's token, or ours with something added, is not ours.
        [answer(RECORD + "x"), answer(RECORD + "x")],
    ],
)
def test_absent_when_both_answered_and_not_both_saw_it(answers):
    """One resolver alone never verifies a domain."""
    assert rules.classify(answers, TOKEN).result == "absent"


@pytest.mark.parametrize(
    "answers",
    [[FAILED, answer(RECORD)], [answer(RECORD), FAILED], [FAILED, FAILED], []],
)
def test_unknown_when_a_resolver_could_not_be_asked(answers):
    assert rules.classify(answers, TOKEN).result == "unknown"


# --- what a check does to a claim ---------------------------------------------------------


def test_a_pending_claim_is_verified_when_found():
    move = rules.after_check("pending", 0, "found")

    assert move == rules.Transition("verified", 0, verified_now=True)


@pytest.mark.parametrize("result", ["absent", "unknown", "taken"])
def test_a_pending_claim_otherwise_stays_pending(result):
    assert rules.after_check("pending", 0, result) == rules.Transition("pending", 0)


def test_a_verified_domain_found_again_starts_its_count_afresh():
    assert rules.after_check("verified", 2, "found") == rules.Transition("verified", 0)


def test_an_outage_never_counts_against_a_verified_domain():
    assert rules.after_check("verified", 2, "unknown") == rules.Transition("verified", 2)


def test_a_verified_domain_lapses_on_the_third_absent_check_in_a_row():
    first = rules.after_check("verified", 0, "absent")
    second = rules.after_check("verified", first.consecutive_absent, "absent")
    third = rules.after_check("verified", second.consecutive_absent, "absent")

    assert (first.status, first.consecutive_absent) == ("verified", 1)
    assert (second.status, second.consecutive_absent) == ("verified", 2)
    assert third == rules.Transition("lapsed", MAX_ABSENT_CHECKS, lapsed_now=True)


@pytest.mark.parametrize("result", ["found", "absent", "unknown", "taken"])
def test_a_lapsed_claim_is_never_revived(result):
    """A domain that changed hands must never inherit an old verification."""
    assert rules.after_check("lapsed", 3, result) == rules.Transition("lapsed", 3)


def test_a_verified_domain_is_checked_again_a_day_after_its_last_check():
    assert not rules.is_recheck_due(
        "verified", NOW - timedelta(hours=23, minutes=59), NOW
    )
    assert rules.is_recheck_due("verified", NOW - timedelta(hours=24), NOW)
    assert not rules.is_recheck_due("pending", NOW - timedelta(days=3), NOW)
    assert not rules.is_recheck_due("verified", None, NOW)
