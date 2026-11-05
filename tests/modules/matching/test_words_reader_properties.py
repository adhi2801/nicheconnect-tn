"""What holds for every sentence the reader is given (item 64, D-158).

Two kinds, as testing.md section 6 asks. For any text at all: it never fails,
every filter is one the search route takes, and nothing it reports was not
in the words. For any search a brand could mean, written in any order and
any of the ways the rules know: reading it gives back exactly that search,
with nothing left over.
"""

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.taxonomy import NICHES
from app.modules.matching.words_reader import (
    FORMAT_WORDS,
    MAX_FOLLOWERS,
    MAX_PRICE_PAISE,
    MONTHS,
    NICHE_WORDS,
    PHRASE_LENGTH,
    PLATFORM_WORDS,
    UNITS,
    Filters,
    place_key,
    read,
)

TODAY = date(2026, 11, 5)
PLACES = ["Madurai", "Coimbatore", "Salem", "Tiruchirappalli", "Kanyakumari"]
CITIES = {place_key(p): p for p in PLACES}
MONTH_WORDS = sorted(MONTHS)


def shape(text: str) -> str:
    return " ".join(text.split())


def holds_for(words: str) -> None:
    r = read(words, cities=CITIES, today=TODAY)
    f = r.filters

    assert f.niche is None or f.niche in NICHES
    assert f.city is None or f.city in PLACES
    assert f.q is None or PHRASE_LENGTH[0] <= len(f.q) <= PHRASE_LENGTH[1]
    for followers in (f.min_followers, f.max_followers):
        assert followers is None or 0 <= followers <= MAX_FOLLOWERS
    if f.min_followers is not None and f.max_followers is not None:
        assert f.min_followers <= f.max_followers
    assert f.max_price_paise is None or 1 <= f.max_price_paise <= MAX_PRICE_PAISE
    assert f.available_on is None or f.available_on >= TODAY
    for said in [p.words for p in r.parts] + list(r.unread) + [n.words for n in r.notes]:
        assert said and said in shape(words), said


@given(st.text(max_size=200))
def test_any_text_reads_into_filters_search_takes(words):
    holds_for(words)


# Plain random text rarely forms a number, a unit and a range at once; this
# alphabet makes it do so constantly, with the lookalike letters thrown in.
@given(
    st.text(
        alphabet="0123456789kKlLmM,./+-₹ toandfollowers\u0130\u0131\u017f\u212a",
        max_size=60,
    )
)
def test_number_heavy_text_reads_into_filters_search_takes(words):
    holds_for(words)


@given(
    st.lists(
        st.sampled_from(
            [
                *MONTH_WORDS,
                *sorted(UNITS),
                *sorted(PLATFORM_WORDS),
                "free",
                "on",
                "1",
                "14",
                "2027",
                "₹",
                "to",
            ]
        ),
        max_size=12,
    ).map(" ".join),
    st.sampled_from([str.upper, str.title, lambda s: s.replace("i", "\u0130")]),
)
def test_the_rules_own_words_in_any_case_read_into_filters_search_takes(words, case):
    holds_for(case(words))


def rendered_count(n: int, unit: bool) -> str:
    if unit and n >= 1000 and n % 1000 == 0:
        return f"{n // 1000}k"
    return f"{n:,}" if n >= 1000 else str(n)


MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


@st.composite
def searches(draw) -> tuple[Filters, str]:
    """A search a brand could mean, and one way of writing it."""
    f = Filters()
    phrases: list[str] = []
    if draw(st.booleans()):
        f.niche = draw(st.sampled_from(NICHES))
        phrases.append(draw(st.sampled_from(NICHE_WORDS[f.niche])) + " creators")
    if draw(st.booleans()):
        f.city = draw(st.sampled_from(PLACES))
        lead = draw(st.sampled_from(["in ", "from ", "based in ", ""]))
        phrases.append(lead + f.city)
    audience = draw(st.sampled_from(["none", "range", "from", "up to"]))
    unit = draw(st.booleans())  # both ends written alike: "5 to 20k" is read as 5k
    word = draw(st.sampled_from(["followers", "subscribers"]))
    if audience == "range":
        low = draw(st.integers(0, MAX_FOLLOWERS))
        high = draw(st.integers(low, MAX_FOLLOWERS))
        f.min_followers, f.max_followers = low, high
        # A unit on both ends or neither: "1 to 15625k" means 1k to 15,625k
        # by the rule people write by, so it is not a way of writing 1.
        both = unit and all(n >= 1000 and n % 1000 == 0 for n in (low, high))
        phrases.append(
            f"{rendered_count(low, both)} to {rendered_count(high, both)} {word}"
        )
    elif audience == "from":
        f.min_followers = draw(st.integers(0, MAX_FOLLOWERS))
        phrases.append(f"over {rendered_count(f.min_followers, unit)} {word}")
    elif audience == "up to":
        f.max_followers = draw(st.integers(0, MAX_FOLLOWERS))
        phrases.append(f"under {rendered_count(f.max_followers, unit)} {word}")
    if draw(st.booleans()):
        rupees = draw(st.integers(1, MAX_PRICE_PAISE // 100))
        f.max_price_paise = rupees * 100
        amount = rendered_count(rupees, draw(st.booleans()))
        phrases.append(
            draw(
                st.sampled_from(
                    [f"under ₹{amount}", f"up to Rs {amount}", f"budget {amount}"]
                )
            )
        )
    if draw(st.booleans()):
        said = draw(st.sampled_from(sorted(PLATFORM_WORDS)))
        f.platform = PLATFORM_WORDS[said]  # type: ignore[assignment]
        phrases.append(f"on {said}")
    if draw(st.booleans()):
        said = draw(st.sampled_from(sorted(FORMAT_WORDS)))
        f.format = FORMAT_WORDS[said]  # type: ignore[assignment]
        phrases.append(said)
    if draw(st.booleans()):
        day = TODAY + timedelta(days=draw(st.integers(0, 2000)))
        f.available_on = day
        month = MONTH_NAMES[day.month - 1]
        written = [
            day.isoformat(),
            f"{day.day} {month} {day.year}",
            f"{month} {day.day} {day.year}",
            f"{day.day}/{day.month}/{day.year}",
        ]
        if day < TODAY.replace(year=TODAY.year + 1):
            written += [f"{day.day} {month}", f"{month[:3]} {day.day}"]
        phrases.append("free on " + draw(st.sampled_from(written)))
    if draw(st.booleans()):
        f.q = draw(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=20)
        )
        phrases.append(f'"{f.q}"')
    order = draw(st.permutations(phrases))
    joiner = draw(st.sampled_from([", ", " ", "; "]))
    return f, joiner.join(order)


@given(searches())
def test_any_search_written_any_way_reads_back_exactly(search):
    meant, words = search

    r = read(words, cities=CITIES, today=TODAY)

    assert r.filters == meant, words
    assert r.unread == (), words
