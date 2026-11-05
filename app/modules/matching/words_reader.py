"""A brand's plain words read as creator-search filters (item 64, D-158).

"Café creators in Coimbatore, 5k to 20k followers, free on 14 November"
becomes niche food, city Coimbatore, 5,000 to 20,000 followers and available
on 14 November, and each filter names the words it came from, so a brand sees
exactly how it was read and can correct it.

Rules, not a model: instant, the words never leave our servers, and the same
words always read the same way. What the rules cannot read is handed back as
unread, never guessed, and a note says why where there is a reason (a whole
month, a second niche, "micro influencers" without numbers).

Every filter it returns is one `GET /api/v1/creators` accepts, within that
route's own limits: the property tests hold it to that for any input.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from app.core.taxonomy import Niche
from app.modules.auth.schemas import ChannelPlatform, PackageFormat

Filter = Literal[
    "q",
    "niche",
    "city",
    "platform",
    "min_followers",
    "max_followers",
    "max_price_paise",
    "format",
    "available_on",
]
NoteCode = Literal[
    "one_phrase",
    "one_day",
    "a_month_is_not_a_day",
    "day_has_passed",
    "not_a_real_day",
    "free_needs_a_day",
    "one_price",
    "price_from_not_searchable",
    "one_follower_range",
    "number_out_of_range",
    "tier_needs_numbers",
    "one_platform",
    "one_format",
    "one_niche",
    "one_city",
]

MAX_WORDS_LENGTH = 200
# The search route's own limits (search_router), repeated here so the reader
# never hands back a filter that route refuses; a test ties the two.
MAX_FOLLOWERS = 1_000_000_000
MAX_PRICE_PAISE = 10_000_000_000
PHRASE_LENGTH = (2, 60)


@dataclass
class Filters:
    q: str | None = None
    niche: Niche | None = None
    city: str | None = None
    platform: ChannelPlatform | None = None
    min_followers: int | None = None
    max_followers: int | None = None
    max_price_paise: int | None = None
    format: PackageFormat | None = None
    available_on: date | None = None


@dataclass(frozen=True)
class Part:
    """Some of the brand's words, as written, and the filter they became."""

    words: str
    filter: Filter
    value: str


@dataclass(frozen=True)
class Note:
    code: NoteCode
    words: str


@dataclass(frozen=True)
class Reading:
    filters: Filters
    parts: tuple[Part, ...]
    unread: tuple[str, ...]
    notes: tuple[Note, ...]


# --- vocabulary ---------------------------------------------------------------

NICHE_WORDS: Mapping[Niche, tuple[str, ...]] = {
    "food": (
        "food",
        "foodie",
        "foodies",
        "cafe",
        "cafes",
        "café",
        "cafés",
        "restaurant",
        "restaurants",
        "cooking",
        "cook",
        "recipe",
        "recipes",
        "chef",
        "chefs",
        "baking",
        "bakery",
        "bakeries",
        "street food",
        "biryani",
        "sweets",
        "snacks",
    ),
    "fashion": (
        "fashion",
        "clothing",
        "clothes",
        "apparel",
        "saree",
        "sarees",
        "ethnic wear",
        "streetwear",
        "outfit",
        "outfits",
        "style",
        "jewellery",
        "jewelry",
    ),
    "beauty": (
        "beauty",
        "makeup",
        "make up",
        "make-up",
        "skincare",
        "skin care",
        "cosmetics",
        "haircare",
        "hair care",
        "salon",
        "salons",
    ),
    "tech": (
        "tech",
        "technology",
        "gadget",
        "gadgets",
        "smartphone",
        "smartphones",
        "unboxing",
        "unboxings",
        "software",
        "laptops",
    ),
    "travel": (
        "travel",
        "traveller",
        "travellers",
        "traveler",
        "travelers",
        "trip",
        "trips",
        "tourism",
        "trekking",
    ),
    "fitness": (
        "fitness",
        "gym",
        "gyms",
        "workout",
        "workouts",
        "yoga",
        "sports",
        "nutrition",
        "wellness",
    ),
    "education": (
        "education",
        "educational",
        "study",
        "studying",
        "exam",
        "exams",
        "tutor",
        "tutors",
        "teaching",
        "learning",
        "career",
        "careers",
    ),
    "entertainment": (
        "entertainment",
        "comedy",
        "comedian",
        "comedians",
        "music",
        "musician",
        "musicians",
        "dance",
        "dancer",
        "dancers",
        "movie",
        "movies",
        "cinema",
        "film",
        "films",
        "gaming",
        "gamer",
        "gamers",
    ),
    "finance": (
        "finance",
        "money",
        "investing",
        "investment",
        "investments",
        "stocks",
        "personal finance",
        "trading",
    ),
    "lifestyle": (
        "lifestyle",
        "home decor",
        "family",
        "parenting",
        "mom",
        "moms",
        "vlog",
        "vlogs",
        "vlogger",
        "vloggers",
        "wedding",
        "weddings",
    ),
}
PLATFORM_WORDS: Mapping[str, str] = {
    "instagram": "instagram",
    "insta": "instagram",
    "ig": "instagram",
    "instagrammer": "instagram",
    "instagrammers": "instagram",
    "youtube": "youtube",
    "you tube": "youtube",
    "yt": "youtube",
    "youtuber": "youtube",
    "youtubers": "youtube",
}
FORMAT_WORDS: Mapping[str, str] = {
    "reel": "reel",
    "reels": "reel",
    "post": "post",
    "posts": "post",
    "story": "story",
    "stories": "story",
    "short": "short",
    "shorts": "short",
    "video": "video",
    "videos": "video",
    # Not "live" alone: "creators who live in Chennai".
    "livestream": "live",
    "livestreams": "live",
    "live stream": "live",
    "live streams": "live",
}
# Words a search sentence is held together by, dropped without comment.
# "Tamil Nadu" too: every creator here is in it. "Tamil" alone is kept as
# unread: it may mean a language, which search cannot filter on.
FILLER = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "with",
        "who",
        "whom",
        "that",
        "which",
        "is",
        "are",
        "be",
        "can",
        "could",
        "would",
        "will",
        "do",
        "does",
        "doing",
        "make",
        "makes",
        "making",
        "making",
        "please",
        "only",
        "also",
        "me",
        "us",
        "we",
        "our",
        "my",
        "i",
        "find",
        "show",
        "search",
        "searching",
        "looking",
        "look",
        "need",
        "want",
        "get",
        "give",
        "each",
        "per",
        "what",
        "campaign",
        "campaigns",
        "collab",
        "collabs",
        "collaboration",
        "promote",
        "promoting",
        "promotion",
        "brand",
        "some",
        "any",
        "all",
        "good",
        "great",
        "best",
        "top",
        "new",
        "nice",
        "local",
        "based",
        "around",
        "near",
        "within",
        "creator",
        "creators",
        "influencer",
        "influencers",
        "people",
        "person",
        "folks",
        "account",
        "accounts",
        "page",
        "pages",
        "channel",
        "channels",
        "handle",
        "handles",
        "profile",
        "profiles",
        "content",
        "tamilnadu",
        "tn",
    ]
)
FILLER_PHRASES = ("tamil nadu",)
TIERS = ("nano", "micro", "macro", "mega", "mid-tier", "mid tier")

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
UNITS = {
    "k": 1_000,
    "thousand": 1_000,
    "l": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "m": 1_000_000,
    "mn": 1_000_000,
    "million": 1_000_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
}

# --- patterns -----------------------------------------------------------------

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_UNIT = "|".join(sorted(UNITS, key=len, reverse=True))
_NUM = r"\d+(?:,\d+)*(?:\.\d+)?"
_AMOUNT = rf"({_NUM})\s?({_UNIT})?\b"
_AUDIENCE = r"(?:followers?|subscribers?|subs|fans|audience|following)\b"
_FREE = r"(?:(?:free|available|open)\s+(?:on\s+)?|on\s+)?"
_ORD = r"(?:st|nd|rd|th)?"

QUOTED = re.compile(r"[\"“”]([^\"“”]*)[\"“”]")
# A year after a day: "14 November 2027". Never a number that goes on to be
# an audience or a range: in "November 14, 2050 to 5000 followers", 2050 is
# followers.
_YEAR = rf"(20\d{{2}})\b(?!\s*(?:(?:{_UNIT})\b|to\b|and\b|[-+\u2013\u2014]|{_AUDIENCE}))"
DATES = (
    ("iso", re.compile(rf"\b{_FREE}(\d{{4}})-(\d{{1,2}})-(\d{{1,2}})\b", re.I)),
    (
        "dmy",
        re.compile(rf"\b{_FREE}(\d{{1,2}})/(\d{{1,2}})(?:/(\d{{4}}|\d{{2}}))?\b", re.I),
    ),
    (
        "dm",
        re.compile(
            rf"\b{_FREE}(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MONTH})\b(?:,?\s+{_YEAR})?",
            re.I,
        ),
    ),
    (
        "md",
        re.compile(rf"\b{_FREE}({_MONTH})\s+(\d{{1,2}}){_ORD}\b(?:,?\s+{_YEAR})?", re.I),
    ),
    ("word", re.compile(rf"\b{_FREE}(today|tomorrow)\b", re.I)),
)
MONTH_ONLY = re.compile(
    rf"\b(?:(?:free|available|open)\s+)?(?:in|during|for|through|all of|this|next)\s+({_MONTH})\b(?:\s+{_YEAR})?",
    re.I,
)
_CURRENCY = r"(?:₹|(?<!\w)rs\.?|(?<!\w)inr)"
_PRICE_UP = r"\b(?:under|below|less than|max(?:imum)?|up ?to|within|at most|budget(?:\s+(?:of|is))?|for|at|around|about)"
_PRICE_FROM = r"\b(?:over|above|more than|at least|min(?:imum)?|from|starting(?:\s+at)?)"
PRICE_RANGE = re.compile(
    rf"(?:{_PRICE_UP}\s+)?{_CURRENCY}\s?{_AMOUNT}\s*(?:to|-|\u2013|\u2014)\s*{_CURRENCY}?\s?{_AMOUNT}(?:\s*/-)?",
    re.I,
)
PRICE = re.compile(
    rf"(?:({_PRICE_FROM})\s+|{_PRICE_UP}\s+)?(?:{_CURRENCY}\s?{_AMOUNT}(?:\s*/-)?|{_AMOUNT}\s?(?:rupees|rs\b|inr\b))",
    re.I,
)
BUDGET = re.compile(rf"\bbudget(?:\s+(?:of|is))?:?\s+{_AMOUNT}", re.I)
FOLLOWER_RANGE = re.compile(
    rf"(?:\bbetween\s+)?\b{_AMOUNT}\s*(?:to|-|\u2013|\u2014|and)\s*{_AMOUNT}\s*\+?\s*({_AUDIENCE})?",
    re.I,
)
FOLLOWERS_FROM = re.compile(
    rf"(?:(?:\b(?:over|above|more than|at least|min(?:imum)?|from)|>=?)\s*\b{_AMOUNT}\s*\+?|\b{_AMOUNT}\s*\+)\s*({_AUDIENCE})?",
    re.I,
)
FOLLOWERS_UP = re.compile(
    rf"(?:\b(?:under|below|less than|at most|max(?:imum)?|up ?to|upto)|<=?)\s*\b{_AMOUNT}\s*({_AUDIENCE})?",
    re.I,
)
FOLLOWERS_BARE = re.compile(rf"\b{_AMOUNT}\s*{_AUDIENCE}", re.I)
TIER = re.compile(
    rf"\b(?:{'|'.join(re.escape(t) for t in TIERS)})(?:[\s-]*(?:influencers?|creators?))?\b",
    re.I,
)
PLACE_LEAD = r"(?:(?:based\s+)?(?:in|from|around|near|at)\s+)?"


def _alternatives(words: Iterable[str]) -> str:
    """A regex alternation of fixed words or phrases, longest first."""
    phrases = sorted(set(words), key=len, reverse=True)
    return "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in phrases)


PLATFORMS = re.compile(rf"\b(?:on\s+)?({_alternatives(PLATFORM_WORDS)})\b", re.I)
FORMATS = re.compile(rf"\b({_alternatives(FORMAT_WORDS)})\b", re.I)
_NICHE_OF = {w: niche for niche, words in NICHE_WORDS.items() for w in words}
NICHES = re.compile(rf"(?<!\w)({_alternatives(_NICHE_OF)})(?!\w)", re.I)
FILLER_PHRASE = re.compile(rf"\b(?:{_alternatives(FILLER_PHRASES)})\b", re.I)
TOKEN = re.compile(r"[^\s,;:!?()\[\]{}]+")


# --- the reader ---------------------------------------------------------------


def _shape(text: str) -> str:
    return " ".join(text.split()).strip(" .,;:-")


# Case-insensitive matching treats these as the ASCII letters they look like
# ("\u0130nsta", a dotted capital I, matches "insta"), but casefold() leaves the first two apart, so a
# lookup by the matched words would miss: folded here, the way the matcher sees them.
_LIKE_ASCII = str.maketrans({"\u0130": "i", "\u0131": "i", "\u00e9": "e"})


def _key(text: str) -> str:
    return " ".join(
        text.casefold().replace("i\u0307", "i").translate(_LIKE_ASCII).split()
    )


def _amount(number: str, unit: str | None) -> Decimal | None:
    try:
        value = Decimal(number.replace(",", ""))
    except InvalidOperation:  # pragma: no cover - the pattern admits only digits
        return None
    return value * UNITS[_key(unit)] if unit else value


def _whole(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


@dataclass
class _Reader:
    text: str
    cities: Mapping[str, str]
    today: date
    rest: list[str] = field(init=False)
    filters: Filters = field(default_factory=Filters)
    parts: list[tuple[int, Part]] = field(default_factory=list)
    unread: list[tuple[int, str]] = field(default_factory=list)
    notes: list[tuple[int, Note]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rest = list(self.text)

    def remaining(self) -> str:
        return "".join(self.rest)

    def take(self, match: re.Match[str]) -> str:
        """The matched words, as written, now consumed."""
        start, end = match.span()
        for i in range(start, end):
            self.rest[i] = " "
        return _shape(self.text[start:end])

    def put(self, at: int, words: str, name: Filter, value: object) -> None:
        if getattr(self.filters, name) is None:
            setattr(self.filters, name, value)
        shown = value.isoformat() if isinstance(value, date) else str(value)
        self.parts.append((at, Part(words, name, shown)))

    def refuse(self, at: int, words: str, code: NoteCode | None) -> None:
        self.unread.append((at, words))
        if code is not None:
            self.notes.append((at, Note(code, words)))

    # Each pass reads one kind of thing and consumes its words, so a later
    # pass never reads them twice. Dates come before numbers ("14 November"
    # is not 14 followers), money before followers (₹10k is not an audience).

    def phrases(self) -> None:
        for match in QUOTED.finditer(self.remaining()):
            words, inner = self.take(match), _shape(match.group(1))
            low, high = PHRASE_LENGTH
            if not low <= len(inner) <= high:
                self.refuse(match.start(), words, None)
            elif self.filters.q is not None:
                self.refuse(match.start(), words, "one_phrase")
            else:
                self.put(match.start(), words, "q", inner)

    def dates(self) -> None:
        for kind, pattern in DATES:
            for match in pattern.finditer(self.remaining()):
                words = self.take(match)
                day, code = self._day(kind, match.groups())
                if day is None:
                    self.refuse(match.start(), words, code)
                elif self.filters.available_on not in (None, day):
                    self.refuse(match.start(), words, "one_day")
                else:
                    self.put(match.start(), words, "available_on", day)
        for match in MONTH_ONLY.finditer(self.remaining()):
            self.refuse(match.start(), self.take(match), "a_month_is_not_a_day")

    def _day(
        self, kind: str, groups: tuple[str | None, ...]
    ) -> tuple[date | None, NoteCode | None]:
        if kind == "word":
            word = _key(groups[0] or "")
            return self.today + timedelta(days=1 if word == "tomorrow" else 0), None
        if kind == "iso":
            year, month, day = (int(g or 0) for g in groups)
            given_year: int | None = year
        elif kind == "dmy":
            day, month = int(groups[0] or 0), int(groups[1] or 0)
            given_year = int(groups[2]) if groups[2] else None
            if given_year is not None and given_year < 100:
                given_year += 2000
        else:
            number, name = (
                (groups[0], groups[1]) if kind == "dm" else (groups[1], groups[0])
            )
            day, month = int(number or 0), MONTHS[_key(name or "")]
            given_year = int(groups[2]) if groups[2] else None
        try:
            found = date(given_year or self.today.year, month, day)
        except ValueError:
            return None, "not_a_real_day"
        if given_year is None and found < self.today:
            try:
                found = date(self.today.year + 1, month, day)
            except ValueError:  # 29 February, already gone this year
                return None, "not_a_real_day"
        if found < self.today:
            return None, "day_has_passed"
        return found, None

    def prices(self) -> None:
        for match in PRICE_RANGE.finditer(self.remaining()):
            words = self.take(match)
            low = _amount(match.group(1), match.group(2))
            high = _amount(match.group(3), match.group(4) or match.group(2))
            self._price(match.start(), words, max(low or Decimal(0), high or Decimal(0)))
        for match in PRICE.finditer(self.remaining()):
            words = self.take(match)
            if match.group(1):
                self.refuse(match.start(), words, "price_from_not_searchable")
                continue
            number, unit = (
                (match.group(2), match.group(3))
                if match.group(2)
                else (match.group(4), match.group(5))
            )
            self._price(match.start(), words, _amount(number, unit))
        for match in BUDGET.finditer(self.remaining()):
            self._price(
                match.start(), self.take(match), _amount(match.group(1), match.group(2))
            )

    def _price(self, at: int, words: str, rupees: Decimal | None) -> None:
        paise = _whole(rupees * 100) if rupees is not None else 0
        if not 1 <= paise <= MAX_PRICE_PAISE:
            self.refuse(at, words, "number_out_of_range")
        elif self.filters.max_price_paise not in (None, paise):
            self.refuse(at, words, "one_price")
        else:
            self.put(at, words, "max_price_paise", paise)

    def followers(self) -> None:
        for match in FOLLOWER_RANGE.finditer(self.remaining()):
            first_unit, second_unit, audience = (
                match.group(2),
                match.group(4),
                match.group(5),
            )
            if not (audience or first_unit or second_unit):
                continue  # "5 to 10" with nothing to say it is an audience
            words = self.take(match)
            high = _amount(match.group(3), second_unit)
            low = _amount(match.group(1), first_unit)
            if (
                first_unit is None
                and second_unit is not None
                and low is not None
                and high is not None
            ):
                # "5 to 20k" means 5,000 to 20,000; "500 to 20k" stays 500.
                scaled = low * UNITS[_key(second_unit)]
                low = scaled if scaled <= high else low
            self._audience(match.start(), words, low, high)
        for pattern, side in (
            (FOLLOWERS_FROM, "min"),
            (FOLLOWERS_UP, "max"),
            (FOLLOWERS_BARE, "min"),
        ):
            for match in pattern.finditer(self.remaining()):
                number, unit = self._first_amount(match)
                audience = pattern is FOLLOWERS_BARE or match.groups()[-1]
                if not (unit or audience):
                    continue  # "over 50" says nothing about followers
                words = self.take(match)
                value = _amount(number, unit)
                if side == "min":
                    self._audience(match.start(), words, value, None)
                else:
                    self._audience(match.start(), words, None, value)
        for match in TIER.finditer(self.remaining()):
            self.refuse(match.start(), self.take(match), "tier_needs_numbers")

    @staticmethod
    def _first_amount(match: re.Match[str]) -> tuple[str, str | None]:
        groups = match.groups()
        pairs = [(groups[i], groups[i + 1]) for i in range(0, len(groups) - 1, 2)]
        return next((n, u) for n, u in pairs if n)

    def _audience(
        self, at: int, words: str, low: Decimal | None, high: Decimal | None
    ) -> None:
        values = [_whole(v) for v in (low, high) if v is not None]
        if any(not 0 <= v <= MAX_FOLLOWERS for v in values):
            self.refuse(at, words, "number_out_of_range")
            return
        least, most = (
            (None if low is None else _whole(low)),
            (None if high is None else _whole(high)),
        )
        if least is not None and most is not None and least > most:
            least, most = most, least  # "20k to 5k" is still the range 5k to 20k
        taken = (self.filters.min_followers, self.filters.max_followers)
        if (least is not None and taken[0] is not None) or (
            most is not None and taken[1] is not None
        ):
            self.refuse(at, words, "one_follower_range")
            return
        if least is not None and taken[1] is not None and least > taken[1]:
            self.refuse(at, words, "one_follower_range")
            return
        if most is not None and taken[0] is not None and most < taken[0]:
            self.refuse(at, words, "one_follower_range")
            return
        if least is not None:
            self.put(at, words, "min_followers", least)
        if most is not None:
            self.put(at, words, "max_followers", most)

    def platforms_and_formats(self) -> None:
        for match in PLATFORMS.finditer(self.remaining()):
            words, value = self.take(match), PLATFORM_WORDS[_key(match.group(1))]
            if self.filters.platform not in (None, value):
                self.refuse(match.start(), words, "one_platform")
            else:
                self.put(match.start(), words, "platform", value)
        for match in FORMATS.finditer(self.remaining()):
            words, value = self.take(match), FORMAT_WORDS[_key(match.group(1))]
            if self.filters.format not in (None, value):
                self.refuse(match.start(), words, "one_format")
            else:
                self.put(match.start(), words, "format", value)

    def niches(self) -> None:
        for match in NICHES.finditer(self.remaining()):
            words, value = self.take(match), _NICHE_OF[_key(match.group(1))]
            if self.filters.niche not in (None, value):
                self.refuse(match.start(), words, "one_niche")
            else:
                self.put(match.start(), words, "niche", value)

    def places(self) -> None:
        names = [n for n in self.cities if n not in FILLER and len(n) >= 2]
        if not names:
            return
        pattern = re.compile(rf"(?<!\w){PLACE_LEAD}({_alternatives(names)})(?!\w)", re.I)
        for match in pattern.finditer(self.remaining()):
            words, value = self.take(match), self.cities[_key(match.group(1))]
            if self.filters.city not in (None, value):
                self.refuse(match.start(), words, "one_city")
            else:
                self.put(match.start(), words, "city", value)

    def leftovers(self) -> None:
        for match in FILLER_PHRASE.finditer(self.remaining()):
            self.take(match)
        for match in TOKEN.finditer(self.remaining()):
            word = _shape(match.group())
            if not any(ch.isalnum() for ch in word) or _key(word) in FILLER:
                continue
            if _key(word) in ("free", "available", "open"):
                self.refuse(match.start(), word, "free_needs_a_day")
            else:
                self.refuse(match.start(), word, None)

    def reading(self) -> Reading:
        for step in (
            self.phrases,
            self.dates,
            self.prices,
            self.followers,
            self.platforms_and_formats,
            self.niches,
            self.places,
            self.leftovers,
        ):
            step()

        def in_order[T](found: list[tuple[int, T]]) -> tuple[T, ...]:
            return tuple(item for _, item in sorted(found, key=lambda x: x[0]))

        return Reading(
            filters=self.filters,
            parts=in_order(self.parts),
            unread=in_order(self.unread),
            notes=in_order(self.notes),
        )


def read(words: str, *, cities: Mapping[str, str], today: date) -> Reading:
    """The filters `words` ask for, how each was read, and what was not.

    `cities` maps a place name, folded by `place_key`, to the spelling search
    should be sent; `today` is the Tamil Nadu day, for dates without a year.
    """
    return _Reader(words[:MAX_WORDS_LENGTH], cities, today).reading()


def place_key(name: str) -> str:
    """How a place name is compared: case, accents and spacing ignored."""
    return _key(name)
