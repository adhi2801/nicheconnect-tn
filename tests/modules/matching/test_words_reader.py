"""The rules that read a brand's words as search filters (item 64, D-158).

Fixed examples: what each kind of words becomes, what each note is for, and
the traps a looser reader falls into ("creators who live in Chennai" is not
a format, "before ₹500" is not "for ₹500", "running a campaign" is not
fitness). What must hold for every input is `test_words_reader_properties.py`.
"""

from datetime import date

import pytest

from app.modules.matching.words_reader import place_key, read

TODAY = date(2026, 11, 5)
CITIES = {
    place_key(name): spelled
    for name, spelled in [
        ("Coimbatore", "Coimbatore"),
        ("Kovai", "Coimbatore"),
        ("Madurai", "Madurai"),
        ("Chennai", "Chennai"),
        ("Tiruchirappalli", "Trichy"),
        ("Trichy", "Trichy"),
        ("in", "In"),  # a creator who typed a word as a city
    ]
}


def filters(words: str) -> dict:
    found = read(words, cities=CITIES, today=TODAY).filters
    return {k: v for k, v in vars(found).items() if v is not None}


def left(words: str) -> tuple[tuple[str, ...], list[tuple[str, str]]]:
    r = read(words, cities=CITIES, today=TODAY)
    return r.unread, [(n.code, n.words) for n in r.notes]


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("food creators", {"niche": "food"}),
        ("Café owners", {"niche": "food"}),
        ("cafes", {"niche": "food"}),
        ("street food", {"niche": "food"}),
        ("skin care", {"niche": "beauty"}),
        ("make-up artists", {"niche": "beauty"}),
        ("personal finance", {"niche": "finance"}),
        ("comedians", {"niche": "entertainment"}),
        ("home decor", {"niche": "lifestyle"}),
    ],
)
def test_niches_from_the_words_people_use(words, expected):
    assert filters(words) == expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("in Coimbatore", {"city": "Coimbatore"}),
        ("from kovai", {"city": "Coimbatore"}),
        ("based in Madurai", {"city": "Madurai"}),
        ("Tiruchirappalli", {"city": "Trichy"}),
        ("CHENNAI", {"city": "Chennai"}),
    ],
)
def test_places_from_the_names_given(words, expected):
    assert filters(words) == expected


def test_a_filler_word_a_creator_typed_as_a_city_is_never_a_place():
    """A creator typed "in" as a city; "in" before an unknown place stays a word."""
    assert filters("food creators in Ooty") == {"niche": "food"}


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("5k to 20k followers", (5_000, 20_000)),
        ("5k-20k", (5_000, 20_000)),
        ("between 5,000 and 20,000 followers", (5_000, 20_000)),
        ("5 to 20k followers", (5_000, 20_000)),
        ("500 to 20k followers", (500, 20_000)),
        ("20k to 5k followers", (5_000, 20_000)),
        ("1.5 lakh to 3 lakh subscribers", (150_000, 300_000)),
        ("1L to 2L", (100_000, 200_000)),
        ("2 to 3 million followers", (2_000_000, 3_000_000)),
    ],
)
def test_a_follower_range(words, expected):
    found = filters(words)
    assert (found["min_followers"], found["max_followers"]) == expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("over 10k followers", {"min_followers": 10_000}),
        ("at least 1 lakh", {"min_followers": 100_000}),
        ("10k+", {"min_followers": 10_000}),
        ("50000 followers", {"min_followers": 50_000}),
        ("under 50k followers", {"max_followers": 50_000}),
        ("up to 2 lakh subscribers", {"max_followers": 200_000}),
    ],
)
def test_one_side_of_an_audience(words, expected):
    assert filters(words) == expected


@pytest.mark.parametrize("words", ["5 to 10", "over 50", "under 300"])
def test_a_number_with_nothing_to_say_it_is_an_audience_is_unread(words):
    assert filters(words) == {}


@pytest.mark.parametrize(
    ("words", "paise"),
    [
        ("under ₹10,000", 1_000_000),
        ("up to Rs. 5000", 500_000),
        ("₹8k", 800_000),
        ("budget 25k", 2_500_000),
        ("budget of 1.5 lakh", 15_000_000),
        ("5000 rupees", 500_000),
        ("INR 2,500.50", 250_050),
        ("₹5k-₹15k", 1_500_000),
        ("₹5000/-", 500_000),
    ],
)
def test_a_price_limit(words, paise):
    assert filters(words) == {"max_price_paise": paise}


def test_a_word_inside_another_never_starts_a_price():
    """ "flat" ends in "at": it must not make "at ₹500"."""
    assert left("flat ₹500") == (("flat",), [])
    assert filters("hrs 500") == {}


@pytest.mark.parametrize(
    ("words", "day"),
    [
        ("free on 14 November", date(2026, 11, 14)),
        ("14th Nov", date(2026, 11, 14)),
        ("November 14", date(2026, 11, 14)),
        ("on 2026-12-01", date(2026, 12, 1)),
        ("1/12", date(2026, 12, 1)),
        ("1/12/27", date(2027, 12, 1)),
        ("available on 3 January", date(2027, 1, 3)),
        ("today", TODAY),
        ("free tomorrow", date(2026, 11, 6)),
        ("14 November 2027", date(2027, 11, 14)),
    ],
)
def test_a_day_to_be_free(words, day):
    assert filters(words) == {"available_on": day}


def test_a_number_after_a_day_is_not_its_year_when_it_is_an_audience():
    assert filters("November 14, 2050 to 5000 followers") == {
        "available_on": date(2026, 11, 14),
        "min_followers": 2050,
        "max_followers": 5000,
    }


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("on instagram", {"platform": "instagram"}),
        ("insta", {"platform": "instagram"}),
        ("youtubers", {"platform": "youtube"}),
        ("YouTube shorts", {"platform": "youtube", "format": "short"}),
        ("reels", {"format": "reel"}),
        ("stories", {"format": "story"}),
        ("live streams", {"format": "live"}),
    ],
)
def test_platforms_and_formats(words, expected):
    assert filters(words) == expected


def test_only_quoted_words_search_the_bio():
    assert filters('food "millet laddu"') == {"niche": "food", "q": "millet laddu"}


def test_the_traps_a_looser_reader_falls_into():
    assert filters("creators who live in Chennai") == {"city": "Chennai"}
    assert left("running a campaign at home") == (("running", "home"), [])


@pytest.mark.parametrize(
    ("words", "code", "unread"),
    [
        ("free in December", "a_month_is_not_a_day", "free in December"),
        ("micro influencers", "tier_needs_numbers", "micro influencers"),
        ("from ₹2000", "price_from_not_searchable", "from ₹2000"),
        ("free", "free_needs_a_day", "free"),
        ("3 nov 2025", "day_has_passed", "3 nov 2025"),
        ("31 feb", "not_a_real_day", "31 feb"),
        ("29 february", "not_a_real_day", "29 february"),
        ("₹0", "number_out_of_range", "₹0"),
        (
            "over 2000 million followers",
            "number_out_of_range",
            "over 2000 million followers",
        ),
        ("food and fashion", "one_niche", "fashion"),
        ("Madurai or Chennai", "one_city", "Chennai"),
        ("instagram or youtube", "one_platform", "youtube"),
        ("reels or stories", "one_format", "stories"),
        ("₹5000 or ₹8000", "one_price", "₹8000"),
        ("today or tomorrow", "one_day", "tomorrow"),
        ('"millet" "ragi"', "one_phrase", '"ragi"'),
        (
            "over 10k followers over 20k followers",
            "one_follower_range",
            "over 20k followers",
        ),
    ],
)
def test_what_is_not_used_says_why(words, code, unread):
    found_unread, notes = left(words)
    assert unread in found_unread
    assert (code, unread) in notes


def test_ranges_that_contradict_each_other_keep_the_first():
    found = filters("over 50k followers under 10k followers")
    assert found == {"min_followers": 50_000}
    assert left("over 50k followers under 10k followers")[1] == [
        ("one_follower_range", "under 10k followers")
    ]


def test_a_low_end_above_the_high_end_already_read_is_refused():
    """A bare "50k followers" is read after "under 10k": it must not make 50k to 10k."""
    assert filters("under 10k followers, 50k followers") == {"max_followers": 10_000}
    assert left("under 10k followers, 50k followers")[1] == [
        ("one_follower_range", "50k followers")
    ]


def test_the_same_thing_twice_is_one_filter_and_no_note():
    r = read("food and restaurant creators", cities=CITIES, today=TODAY)
    assert r.filters.niche == "food"
    assert [(p.words, p.value) for p in r.parts] == [
        ("food", "food"),
        ("restaurant", "food"),
    ]
    assert r.notes == ()


def test_unknown_words_come_back_as_written_in_order():
    assert left("Vegan, Tamil-speaking food creators & chefs")[0] == (
        "Vegan",
        "Tamil-speaking",
    )


def test_tamil_nadu_is_where_everyone_is_but_tamil_may_mean_a_language():
    assert left("Tamil Nadu food creators")[0] == ()
    assert left("Tamil food creators")[0] == ("Tamil",)


def test_the_example_in_the_route_s_description():
    r = read(
        "Café creators in Coimbatore, 5k to 20k followers, free on 14 November",
        cities=CITIES,
        today=TODAY,
    )
    assert vars(r.filters) == {
        "q": None,
        "niche": "food",
        "city": "Coimbatore",
        "platform": None,
        "min_followers": 5_000,
        "max_followers": 20_000,
        "max_price_paise": None,
        "format": None,
        "available_on": date(2026, 11, 14),
    }
    assert (r.unread, r.notes) == ((), ())


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("\u0130nsta", {"platform": "instagram"}),
        ("1 m\u0130llion followers", {"min_followers": 1_000_000}),
        ("free on 3 apr\u0130l", {"available_on": date(2027, 4, 3)}),
        ("\u017ftreet food", {"niche": "food"}),
    ],
)
def test_letters_the_matcher_reads_as_ascii_never_break_a_lookup(words, expected):
    """Case-insensitive matching takes "\u0130" for "i"; the lookup must agree, or it raises."""
    found = {
        k: v for k, v in vars(read(words, cities=CITIES, today=TODAY).filters).items()
    }
    assert {k: found[k] for k in expected} == expected


@pytest.mark.parametrize("quoted", ['"x"', '""', '"' + "x" * 61 + '"'])
def test_a_quoted_phrase_search_would_refuse_is_unread(quoted):
    r = read(f"food {quoted}", cities=CITIES, today=TODAY)
    assert (r.filters.q, r.unread) == (None, (quoted,))


def test_29_february_after_it_has_passed_in_a_leap_year_is_not_a_day():
    """2028 has one and it is gone on 1 March; 2029 has none."""
    r = read("free on 29 February", cities=CITIES, today=date(2028, 3, 1))
    assert r.filters.available_on is None
    assert [n.code for n in r.notes] == ["not_a_real_day"]


def test_with_no_places_known_a_place_is_unread():
    r = read("creators in Madurai", cities={}, today=TODAY)
    assert (r.filters.city, r.unread) == (None, ("Madurai",))
