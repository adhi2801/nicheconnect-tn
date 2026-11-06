"""Festival campaign templates (item 14, piece 1, D-161; widened by D-165).

Most brand work in Tamil Nadu follows the year's festivals and seasons. A
brand that starts from "Pongal" gets a campaign already worded for it: a
title, a description, the deliverables and the niches, to edit and publish
as its own. City and budget are the brand's: a template never guesses them.

Every faith in Tamil Nadu, and none: Hindu, Christian and Muslim festivals and
secular seasons, each a moment brands here actually run campaigns for. None is
placed by its faith: the list is ordered only by how soon a brand must publish.

**Dates, and where they come from.** Each template has real occurrences:
- a season or a fixed day (Pongal's Thai, Aadi, Christmas, 1 January) is the
  same days every year;
- a festival that moves is dated year by year in `DATED`, from the Tamil Nadu
  Government's notified public holidays where the year is notified (2026,
  2027), and otherwise from Drik Panchang's Tamil calendar or the consensus
  of published estimates, marked not confirmed;
- Easter is computed by the Church's own rule (`easter_sunday`).
A festival that follows the moon (Ramzan, Bakrid) is never confirmed ahead:
its day depends on the moon being sighted, and the template says so.

The table must always reach a year ahead: `test_the_dates_reach_a_year_ahead`
fails on the real calendar once it does not, so a new year's dates are added
when the Government notifies them (about October each year).

Every template, with a city and a budget added, is a campaign the create
route accepts and the text flags pass: `test_campaign_templates_api.py`.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.taxonomy import Niche
from app.modules.campaigns.schemas import DeliverableFormat, DeliverablePlatform

# Every deliverables line ends with this, so a brand's first draft already asks
# for the label ASCI requires on paid content (legal.md section 3.7).
LABEL = "each labelled as a paid partnership"


@dataclass(frozen=True)
class Item:
    platform: DeliverablePlatform
    format: DeliverableFormat
    quantity: int


@dataclass(frozen=True)
class Occurrence:
    starts_on: date
    ends_on: date
    confirmed: bool


@dataclass(frozen=True)
class FestivalTemplate:
    key: str
    name: str
    when: str
    lead_weeks: int
    title: str
    description: str
    deliverables: str
    items: tuple[Item, ...]
    niches: tuple[Niche, ...]
    # the same month and day every year: ((start month, day), (end month, day));
    # an end before its start runs into the next year
    every_year: tuple[tuple[int, int], tuple[int, int]] | None = None
    moon: bool = field(default=False)


def reels_and_stories(reels: int, stories: int) -> tuple[Item, ...]:
    items = []
    if reels:
        items.append(Item("instagram", "reel", reels))
    if stories:
        items.append(Item("instagram", "story", stories))
    return tuple(items)


TEMPLATES: tuple[FestivalTemplate, ...] = (
    FestivalTemplate(
        key="new_year",
        name="New Year's Day",
        when="1 January",
        lead_weeks=4,
        title="A fresh start for the new year",
        description=(
            "Creators share how they start the year: the night with friends, a new "
            "routine, the first plans, with our product part of the fresh start."
        ),
        deliverables=f"1 Instagram reel on New Year's Day and 2 stories the night before, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("lifestyle", "fitness", "fashion"),
        every_year=((12, 31), (1, 1)),
    ),
    FestivalTemplate(
        key="pongal",
        name="Pongal",
        when="Mid-January: Bhogi, Thai Pongal on the first day of Thai, Mattu and Kaanum Pongal",
        lead_weeks=6,
        title="Pongal with our family of products",
        description=(
            "Creators show how their family gets ready for Pongal and keeps it: the house "
            "cleaned for Bhogi, new clothes, the kolam at the door, the pot on the fire "
            "and the family meal, with our product part of it. Warm, real and unhurried, "
            "never a list of offers."
        ),
        deliverables=(
            f"3 Instagram stories in the days before Pongal and 2 reels across its four days, {LABEL}"
        ),
        items=reels_and_stories(2, 3),
        niches=("food", "lifestyle", "fashion"),
    ),
    FestivalTemplate(
        key="puthandu",
        name="Puthandu, the Tamil New Year",
        when="14 April, the first day of Chithirai",
        lead_weeks=5,
        title="A new year, a fresh start",
        description=(
            "Creators share how they begin the Tamil year: the house cleaned and "
            "decorated, the first meal of the year, a fresh routine, with our product "
            "part of it."
        ),
        deliverables=f"2 Instagram stories the day before Puthandu and 1 reel on the day, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("lifestyle", "food", "beauty"),
        every_year=((4, 14), (4, 14)),
    ),
    FestivalTemplate(
        key="easter",
        name="Easter",
        when="March or April, the Sunday after Good Friday",
        lead_weeks=4,
        title="Easter with the family",
        description=(
            "Creators share their Easter Sunday: new clothes, the family lunch, the "
            "visits to relatives, with our product part of the day."
        ),
        deliverables=f"2 Instagram stories in Easter week and 1 reel on Easter Sunday, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("food", "fashion", "lifestyle"),
    ),
    FestivalTemplate(
        key="ramzan",
        name="Ramzan and Eid",
        when=(
            "The month of fasting and Eid ul-Fitr at its end; about eleven days earlier "
            "each year, and the day depends on the moon being sighted"
        ),
        lead_weeks=5,
        title="Ramzan evenings and Eid",
        description=(
            "Creators share the month: iftar with family and friends, the night "
            "markets, and Eid morning's new clothes and visits, with our product part of it."
        ),
        deliverables=f"3 Instagram stories across the month and 1 reel for Eid, {LABEL}",
        items=reels_and_stories(1, 3),
        niches=("food", "fashion", "lifestyle"),
        moon=True,
    ),
    FestivalTemplate(
        key="bakrid",
        name="Bakrid",
        when=(
            "Eid ul-Adha; about eleven days earlier each year, and the day depends on "
            "the moon being sighted"
        ),
        lead_weeks=4,
        title="Bakrid, shared",
        description=(
            "Creators share the festival as their family keeps it: new clothes, the meal "
            "shared with family and neighbours, the visits, with our product part of it."
        ),
        deliverables=f"2 Instagram stories the day before Bakrid and 1 reel on the day, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("food", "fashion", "lifestyle"),
        moon=True,
    ),
    FestivalTemplate(
        key="back_to_school",
        name="Back to school",
        when="Early June, when schools reopen",
        lead_weeks=4,
        title="Ready for the new school year",
        description=(
            "Parents and students share how they get ready for school reopening, "
            "with our product part of the list."
        ),
        deliverables=f"1 Instagram reel and 2 stories in the two weeks before reopening, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("education", "lifestyle"),
        every_year=((6, 1), (6, 14)),
    ),
    FestivalTemplate(
        key="aadi",
        name="The Aadi season",
        when="Mid-July to mid-August, the month of Aadi",
        lead_weeks=4,
        title="The Aadi season, at its best",
        description=(
            "Aadi is a month Tamil Nadu shops in. Creators show what they would pick "
            "from our range this season and why, in their own words; any offer is "
            "stated exactly as we word it."
        ),
        deliverables=f"2 Instagram reels, one at the start of Aadi and one midway, {LABEL}",
        items=reels_and_stories(2, 0),
        niches=("fashion", "lifestyle"),
        every_year=((7, 17), (8, 16)),
    ),
    FestivalTemplate(
        key="independence_day",
        name="Independence Day",
        when="15 August, and the week of sales before it",
        lead_weeks=4,
        title="The Independence Day week",
        description=(
            "Creators show what they would pick from our range this week and why, in "
            "their own words; any offer is stated exactly as we word it."
        ),
        deliverables=f"1 Instagram reel and 2 stories in the week before 15 August, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("fashion", "tech", "lifestyle"),
        every_year=((8, 8), (8, 15)),
    ),
    FestivalTemplate(
        key="velankanni",
        name="The Velankanni feast",
        when="29 August to 8 September, the feast at Velankanni",
        lead_weeks=4,
        title="On the road to Velankanni",
        description=(
            "Creators share the journey families make to Velankanni for the feast: the "
            "travel, the stops and the food along the way, the town during the feast, "
            "with our product part of the trip."
        ),
        deliverables=f"1 Instagram reel and 3 stories during the feast, {LABEL}",
        items=reels_and_stories(1, 3),
        niches=("travel", "food", "lifestyle"),
        every_year=((8, 29), (9, 8)),
    ),
    FestivalTemplate(
        key="vinayagar_chathurthi",
        name="Vinayagar Chathurthi",
        when="August or September",
        lead_weeks=4,
        title="Vinayagar Chathurthi at home",
        description=(
            "Creators show the festival at home: the kozhukattai made together, the "
            "decorations, the family, with our product part of it."
        ),
        deliverables=f"2 Instagram stories the day before and 1 reel on the day, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("food", "lifestyle"),
    ),
    FestivalTemplate(
        key="navaratri",
        name="Navaratri and Ayudha Pooja",
        when="September or October, nine nights",
        lead_weeks=5,
        title="Nine nights of visits",
        description=(
            "Creators share the nine nights: the visits between homes, the sundal, the "
            "evenings dressed up, and Ayudha Pooja's clean-up, with our product in the season."
        ),
        deliverables=f"3 Instagram stories across the nine nights and 1 reel, {LABEL}",
        items=reels_and_stories(1, 3),
        niches=("fashion", "food", "lifestyle"),
    ),
    FestivalTemplate(
        key="deepavali",
        name="Deepavali",
        when="October or November",
        lead_weeks=6,
        title="Our Deepavali, your way",
        description=(
            "Creators show the run-up and the day: shopping for new clothes, sweets made "
            "and shared, the morning and the evening, with our product part of it."
        ),
        deliverables=(
            f"3 Instagram stories in the two weeks before Deepavali and 2 reels on the day, {LABEL}"
        ),
        items=reels_and_stories(2, 3),
        niches=("fashion", "food", "beauty"),
    ),
    FestivalTemplate(
        key="karthigai_deepam",
        name="Karthigai Deepam",
        when="November or December",
        lead_weeks=4,
        title="Lamps for Karthigai",
        description=(
            "Creators light the house for Karthigai Deepam: rows of agal lamps, the "
            "evening, the family, with our product in the frame."
        ),
        deliverables=f"1 Instagram reel and 2 stories on the evening of Deepam, {LABEL}",
        items=reels_and_stories(1, 2),
        niches=("lifestyle", "food"),
    ),
    FestivalTemplate(
        key="margazhi",
        name="The Margazhi season",
        when="Mid-December to mid-January, Chennai's music and dance season",
        lead_weeks=4,
        title="A Margazhi morning",
        description=(
            "Creators share the season: an early kolam, a concert or a dance recital, "
            "a sabha canteen breakfast, with our product part of their morning."
        ),
        deliverables=f"2 Instagram reels during the season, {LABEL}",
        items=reels_and_stories(2, 0),
        niches=("entertainment", "food", "lifestyle"),
        every_year=((12, 16), (1, 14)),
    ),
    FestivalTemplate(
        key="christmas",
        name="Christmas",
        when="25 December",
        lead_weeks=5,
        title="Christmas together",
        description=(
            "Creators show the run-up and the day: the star outside the house, the "
            "cake, the visits and the gifts, with our product among them."
        ),
        deliverables=(
            f"2 Instagram stories in the week before Christmas and 1 reel on the day, {LABEL}"
        ),
        items=reels_and_stories(1, 2),
        niches=("food", "lifestyle", "fashion"),
        every_year=((12, 24), (12, 25)),
    ),
)


def _d(y: int, m: int, d: int) -> date:
    return date(y, m, d)


# Festivals that move, year by year: (starts_on, ends_on, confirmed).
# G.O. 2026: the Tamil Nadu Government's public holidays for 2026 (DT Next, The Week,
#   November 2025). G.O. 2027: G.O. (Ms.) No. 613 (GoodReturns, 23 October 2026).
# Drik: Drik Panchang's Tamil calendar, read 6 November 2026. Estimates for 2028's
#   Islamic dates: the consensus of published calendars, read 6 November 2026.
# A day the Government notifies is confirmed; a moon-sighted day never is ahead.
DATED: dict[str, tuple[Occurrence, ...]] = {
    "pongal": (
        Occurrence(_d(2027, 1, 14), _d(2027, 1, 17), True),  # G.O. 2027: Pongal 15 Jan
        Occurrence(_d(2028, 1, 14), _d(2028, 1, 17), False),  # Drik: Thai Pongal 15 Jan
    ),
    "ramzan": (
        # the month of fasting, ending with Eid: G.O. 2027 Eid 10 March (moon sighting)
        Occurrence(_d(2027, 2, 9), _d(2027, 3, 10), False),
        Occurrence(_d(2028, 1, 28), _d(2028, 2, 26), False),  # estimates: Eid 26 Feb
    ),
    "bakrid": (
        Occurrence(_d(2027, 5, 17), _d(2027, 5, 17), False),  # G.O. 2027 (moon sighting)
        Occurrence(_d(2028, 5, 5), _d(2028, 5, 5), False),  # estimates
    ),
    "vinayagar_chathurthi": (
        Occurrence(_d(2027, 9, 4), _d(2027, 9, 4), True),  # G.O. 2027
        Occurrence(_d(2028, 8, 23), _d(2028, 8, 23), False),  # Drik
    ),
    "navaratri": (
        # Drik's first night to Vijayadasami; G.O. 2027 Ayudha Pooja 8, Vijayadasami 9 Oct
        Occurrence(_d(2027, 9, 30), _d(2027, 10, 9), True),
        Occurrence(_d(2028, 9, 19), _d(2028, 9, 27), False),  # Drik
    ),
    "deepavali": (
        Occurrence(_d(2026, 11, 8), _d(2026, 11, 8), True),  # G.O. 2026
        Occurrence(_d(2027, 10, 28), _d(2027, 10, 28), True),  # G.O. 2027
        Occurrence(_d(2028, 10, 17), _d(2028, 10, 17), False),  # Drik
    ),
    "karthigai_deepam": (
        # not a public holiday, so never notified: Drik for every year
        Occurrence(_d(2026, 11, 24), _d(2026, 11, 24), False),
        Occurrence(_d(2027, 12, 12), _d(2027, 12, 12), False),
        Occurrence(_d(2028, 12, 1), _d(2028, 12, 1), False),
    ),
}


def easter_sunday(year: int) -> date:
    """Easter Sunday by the Gregorian computus (the anonymous algorithm, as published by
    Meeus): the rule the Church itself fixes the date by, so it is exact for any year."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    weekday = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday) // 451
    n = h + weekday - 7 * m + 114
    return date(year, n // 31, n % 31 + 1)


def occurrences(t: FestivalTemplate, today: date) -> list[Occurrence]:
    """The template's occurrences from last year to next, earliest first."""
    if t.every_year is not None:
        (sm, sd), (em, ed) = t.every_year
        out = []
        for y in (today.year - 1, today.year, today.year + 1):
            start = date(y, sm, sd)
            end = date(y + 1 if (em, ed) < (sm, sd) else y, em, ed)
            out.append(Occurrence(start, end, True))
        return out
    if t.key == "easter":
        return [
            Occurrence(easter_sunday(y) - timedelta(days=2), easter_sunday(y), True)
            for y in (today.year - 1, today.year, today.year + 1)
        ]
    return list(DATED.get(t.key, ()))


def next_occurrence(t: FestivalTemplate, today: date) -> Occurrence | None:
    """The occurrence happening now or next; None when the table does not reach it."""
    return next((o for o in occurrences(t, today) if o.ends_on >= today), None)


def publish_by(t: FestivalTemplate, o: Occurrence) -> date:
    """The day a brand should have the campaign open: its lead weeks before it starts."""
    return o.starts_on - timedelta(weeks=t.lead_weeks)


def upcoming(today: date) -> list[tuple[FestivalTemplate, Occurrence]]:
    """Every template with a known next occurrence, the one to publish soonest first.

    Ordered only by date: by the day to publish by, then the day it starts, then the key,
    so no festival is placed by its faith. One already under way has passed its publish-by
    day and leads the list. A template the table no longer reaches is left out rather than
    given a guessed date; the freshness test keeps that from happening."""
    found = [(t, o) for t in TEMPLATES if (o := next_occurrence(t, today)) is not None]
    return sorted(found, key=lambda to: (publish_by(*to), to[1].starts_on, to[0].key))
