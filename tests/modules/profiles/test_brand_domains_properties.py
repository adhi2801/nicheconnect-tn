"""What holds for every typed domain and every run of checks (item 74; testing.md section 6)."""

import re

from hypothesis import given
from hypothesis import strategies as st

from app.modules.profiles import brand_domains as rules
from app.modules.profiles.brand_domain_models import DOMAIN_PATTERN, MAX_ABSENT_CHECKS

LETTERS = "abcdefghijklmnopqrstuvwxyz0123456789-"
labels = st.text(alphabet=LETTERS, min_size=1, max_size=20)
suffixes = st.sampled_from(["in", "co.in", "com", "org", "net.in", "io", "shop"])
typed = st.one_of(
    st.builds(lambda name, suffix: f"{name}.{suffix}", labels, suffixes),
    st.builds(
        lambda sub, name, suffix: f"{sub}.{name}.{suffix}", labels, labels, suffixes
    ),
    st.text(max_size=40),
)
results = st.lists(st.sampled_from(["found", "absent", "unknown", "taken"]), max_size=30)


@given(typed)
def test_an_accepted_domain_is_always_one_the_database_accepts(text):
    try:
        claimed = rules.registrable_domain(text)
    except rules.DomainNotAccepted:
        return
    assert re.fullmatch(DOMAIN_PATTERN, claimed)
    assert "xn--" not in claimed
    assert claimed == claimed.lower()


@given(typed)
def test_an_accepted_domain_is_its_own_registrable_domain_and_never_a_suffix(text):
    """So no claim is ever to co.in, and nykaa.com.evil.ru is never 'nykaa.com'."""
    try:
        claimed = rules.registrable_domain(text)
    except rules.DomainNotAccepted:
        return
    assert rules.registrable_domain(claimed) == claimed
    assert claimed.count(".") >= 1


@given(results)
def test_a_run_of_checks_always_ends_in_an_allowed_state(sequence):
    status, absent, verified_seen = "pending", 0, False
    for result in sequence:
        move = rules.after_check(status, absent, result)
        # Lapsed only after having been verified, and never revived.
        if status == "lapsed":
            assert move.status == "lapsed"
        if move.status == "lapsed":
            assert verified_seen
        assert 0 <= move.consecutive_absent <= MAX_ABSENT_CHECKS
        status, absent = move.status, move.consecutive_absent
        verified_seen = verified_seen or status == "verified"


@given(results)
def test_only_absent_checks_in_a_row_ever_lapse_a_verified_domain(sequence):
    status, absent, run = "verified", 0, 0
    for result in sequence:
        move = rules.after_check(status, absent, result)
        if status == "verified":
            run = run + 1 if result == "absent" else (run if result == "unknown" else 0)
            assert (move.status == "lapsed") == (run >= MAX_ABSENT_CHECKS)
        status, absent = move.status, move.consecutive_absent
