"""Whether a brand's name looks like a protected brand's (item 75, D-118). Pure rules."""

import pytest

from app.modules.profiles.brand_names import (
    ProtectedName,
    covers,
    curated,
    flag_for,
    resembles,
    slip_distance,
    words,
)

CYRILLIC_U = chr(0x0443)
NYKAA = ProtectedName("Nykaa", "nykaa.com")
PLUM = ProtectedName("Plum", "plumgoodness.com", "exact")
SUGAR = ProtectedName("SUGAR Cosmetics", "sugarcosmetics.com")


@pytest.mark.parametrize(
    "name",
    [
        "Nykaa",
        "NYKAA",
        "Nykaa Collabs",
        "Nykaa Official India",
        "Nykaa Beauty Partners",
        "N" + CYRILLIC_U + "kaa Official",
        "Nykka",
        "Nyka",
        "Nykaa Pvt. Ltd.",
        "The Nykaa Team",
    ],
)
def test_names_that_borrow_nykaa_resemble_it(name):
    assert resembles(name, NYKAA)


@pytest.mark.parametrize(
    "name",
    ["Amma Sweets", "Nayak Textiles", "Chennai Bakes", "Kalyan Silks", "Nylon Works"],
)
def test_ordinary_names_do_not(name):
    assert not resembles(name, NYKAA)


def test_a_name_with_every_letter_it_can_swapped_still_resembles():
    """Three Cyrillic letters are three slips apart; only the skeleton sees them as one."""
    cyrillic_a = chr(0x0430)
    disguised = "N" + CYRILLIC_U + "k" + cyrillic_a + cyrillic_a

    assert slip_distance(disguised.casefold(), "nykaa") == 3
    assert resembles(disguised, NYKAA)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Plum", True),
        ("PLUM", True),
        ("Plum Official", True),
        # Found by the property test: "team" reads "tearn" once "m" is made
        # its look-alike "rn", and was then not dropped as filler.
        ("Plum Team", True),
        ("Plum Cakes Chennai", False),
        ("Plumbing Works", False),
        ("Plus", False),
    ],
)
def test_an_everyday_word_is_matched_only_whole(name, expected):
    assert resembles(name, PLUM) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SUGAR Cosmetics Team", True),
        ("Sugar Cosmetic", True),
        ("Sugar Candy Shop", False),
        ("Cosmetics Sugar", False),
    ],
)
def test_a_two_word_name_matches_in_order(name, expected):
    assert resembles(name, SUGAR) is expected


def test_filler_words_alone_are_not_a_name():
    assert words("Official India Store") == ()
    assert not resembles("Official India Store", NYKAA)


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("nykaa", "nykaa", 0),
        ("nykka", "nykaa", 1),
        ("nyka", "nykaa", 1),
        ("nkyaa", "nykaa", 1),
        ("zomatto", "zomato", 1),
        ("nylon", "nykaa", 3),
        ("", "abc", 3),
    ],
)
def test_slip_distance(a, b, distance):
    assert slip_distance(a, b) == distance


@pytest.mark.parametrize(
    ("verified", "expected"),
    [
        ("nykaa.com", True),
        ("NYKAA.COM", True),
        ("beauty.nykaa.com", True),
        ("nykaa.com.evil.in", False),
        ("notnykaa.com", False),
        (None, False),
    ],
)
def test_only_the_domain_or_its_subdomains_cover_it(verified, expected):
    assert covers(verified, "nykaa.com") is expected


def test_the_real_brand_is_never_flagged_once_its_domain_is_verified():
    assert flag_for("Nykaa", "nykaa.com", [NYKAA]) is None
    assert flag_for("Nykaa Collabs", "nykaa.com", [NYKAA]) is None


def test_an_impersonator_with_its_own_domain_is_still_flagged():
    flag = flag_for("Nykaa Collabs", "nykaa-collabs.in", [NYKAA])

    assert flag is not None and flag.resembles == NYKAA


def test_a_mixed_alphabet_name_is_flagged_without_a_protected_match():
    flag = flag_for("Amm" + chr(0x0430) + " Sweets", None, [NYKAA])

    assert flag is not None
    assert flag.resembles is None and flag.mixed_script


def test_a_plain_name_has_nothing_to_say():
    assert flag_for("Amma Sweets", None, curated()) is None


def test_the_curated_list_is_read_and_each_entry_is_sound():
    """A guard on the data file: names, domains, and a known kind of match."""
    entries = curated()

    assert len(entries) >= 15
    for entry in entries:
        assert words(entry.name), entry
        assert entry.match in ("word", "exact"), entry
        assert entry.domain == entry.domain.lower() and "." in entry.domain, entry
        # A curated brand never resembles a different curated brand.
        assert [other for other in entries if resembles(entry.name, other)] == [entry]


@pytest.mark.parametrize("name", ["Boot", "Bolt", "Coat"])
def test_a_short_name_allows_no_slip(name):
    """One slip from a four-letter name lands on ordinary words."""
    assert not resembles(name, ProtectedName("boAt", "boat-lifestyle.com", "exact"))
