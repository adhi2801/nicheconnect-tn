"""Festival campaign templates (item 14, piece 1, D-161).

Most brand work in Tamil Nadu follows the year's festivals and seasons. A
brand that starts from "Pongal" gets a campaign already worded for it: a
title, a description, the deliverables and the niches, to edit and publish
as its own. City and budget are the brand's: a template never guesses them.

Each template names the months it falls in and how many weeks ahead to
publish. A festival that follows the moon on a calendar other than the
solar one (Ramzan) names none, says so, and is listed last, rather than
being given a month it may not be in. The list starts with the template
coming soonest, from the Tamil Nadu day given.

Every template, with a city and a budget added, is a campaign the create
route accepts and the text flags pass: `test_campaign_templates_api.py`.
"""

from dataclasses import dataclass
from datetime import date

from app.core.taxonomy import Niche


@dataclass(frozen=True)
class FestivalTemplate:
    key: str
    name: str
    when: str
    months: tuple[int, ...]
    lead_weeks: int
    title: str
    description: str
    deliverables: str
    niches: tuple[Niche, ...]


TEMPLATES: tuple[FestivalTemplate, ...] = (
    FestivalTemplate(
        key="pongal",
        name="Pongal",
        when="Mid-January, the first day of the Tamil month of Thai",
        months=(1,),
        lead_weeks=6,
        title="Pongal with our family of products",
        description=(
            "Creators show our product as part of their Pongal at home: the kolam at the "
            "door, the pongal pot boiling over, new clothes and the family meal. Warm, "
            "real and unhurried, never a list of offers."
        ),
        deliverables="2 Instagram reels and 3 stories, live in the week before Pongal",
        niches=("food", "lifestyle", "fashion"),
    ),
    FestivalTemplate(
        key="puthandu",
        name="Puthandu, the Tamil New Year",
        when="Mid-April, the first day of Chithirai",
        months=(4,),
        lead_weeks=5,
        title="A new year, a fresh start",
        description=(
            "Creators share what they begin with the new year: the house cleaned and "
            "decorated, the first meal, a fresh routine, with our product part of it."
        ),
        deliverables="1 Instagram reel and 2 stories, live in the week of Puthandu",
        niches=("lifestyle", "food", "beauty"),
    ),
    FestivalTemplate(
        key="aadi",
        name="Aadi season offers",
        when="Mid-July to mid-August, the month of Aadi",
        months=(7, 8),
        lead_weeks=4,
        title="The Aadi season, at its best",
        description=(
            "Aadi is when Tamil Nadu shops for less. Creators show what they would pick "
            "from our range this season and why, in their own words."
        ),
        deliverables="2 Instagram reels, one at the start of Aadi and one midway",
        niches=("fashion", "lifestyle"),
    ),
    FestivalTemplate(
        key="vinayagar_chathurthi",
        name="Vinayagar Chathurthi",
        when="August or September",
        months=(8, 9),
        lead_weeks=4,
        title="Vinayagar Chathurthi at home",
        description=(
            "Creators show the day as their family keeps it: the clay idol, the "
            "kozhukattai made at home, the decorations, with our product part of it."
        ),
        deliverables="1 Instagram reel and 2 stories, live in the days before the festival",
        niches=("food", "lifestyle"),
    ),
    FestivalTemplate(
        key="navaratri",
        name="Navaratri, Golu and Ayudha Pooja",
        when="September or October, nine nights",
        months=(9, 10),
        lead_weeks=5,
        title="Nine nights of Golu",
        description=(
            "Creators share their Golu steps, the visits, the sundal and the evenings "
            "dressed up, with our product in the season."
        ),
        deliverables="3 Instagram stories across the nine nights and 1 reel",
        niches=("fashion", "food", "lifestyle"),
    ),
    FestivalTemplate(
        key="deepavali",
        name="Deepavali",
        when="October or November",
        months=(10, 11),
        lead_weeks=6,
        title="Our Deepavali, your way",
        description=(
            "Creators show their Deepavali morning: the oil bath, new clothes, sweets "
            "made and shared, and our product as part of the day."
        ),
        deliverables="2 Instagram reels and 3 stories, live in the two weeks before Deepavali",
        niches=("fashion", "food", "beauty"),
    ),
    FestivalTemplate(
        key="karthigai_deepam",
        name="Karthigai Deepam",
        when="November or December",
        months=(11, 12),
        lead_weeks=4,
        title="Lamps for Karthigai",
        description=(
            "Creators light the house for Karthigai Deepam: rows of agal lamps, the "
            "evening, the family, with our product in the frame."
        ),
        deliverables="1 Instagram reel and 2 stories, live on the evening of Deepam",
        niches=("lifestyle", "food"),
    ),
    FestivalTemplate(
        key="margazhi",
        name="The Margazhi season",
        when="Mid-December to mid-January, Chennai's music and dance season",
        months=(12, 1),
        lead_weeks=4,
        title="A Margazhi morning",
        description=(
            "Creators share the season: an early kolam, a concert or a dance recital, "
            "a sabha canteen breakfast, with our product part of their morning."
        ),
        deliverables="2 Instagram reels during the season",
        niches=("entertainment", "food", "lifestyle"),
    ),
    FestivalTemplate(
        key="christmas",
        name="Christmas",
        when="25 December",
        months=(12,),
        lead_weeks=5,
        title="Christmas together",
        description=(
            "Creators show their Christmas: the star outside the house, the cake, "
            "the visits and the gifts, with our product among them."
        ),
        deliverables="1 Instagram reel and 2 stories, live in the week before Christmas",
        niches=("food", "lifestyle", "fashion"),
    ),
    FestivalTemplate(
        key="back_to_school",
        name="Back to school",
        when="June, when schools reopen",
        months=(6,),
        lead_weeks=4,
        title="Ready for the new school year",
        description=(
            "Parents and students share how they get ready for school reopening, "
            "with our product part of the list."
        ),
        deliverables="1 Instagram reel and 2 stories, live in the two weeks before reopening",
        niches=("education", "lifestyle"),
    ),
    FestivalTemplate(
        key="ramzan",
        name="Ramzan and Eid",
        when="Follows the moon: about eleven days earlier each year, so set the dates yourself",
        months=(),
        lead_weeks=5,
        title="Ramzan evenings and Eid",
        description=(
            "Creators share the month: iftar with family and friends, the night "
            "markets, and Eid morning, with our product part of it."
        ),
        deliverables="1 Instagram reel and 3 stories across the month",
        niches=("food", "fashion", "lifestyle"),
    ),
)


def months_until(template: FestivalTemplate, today: date) -> int | None:
    """Whole months from this month to the template's next one: 0 when it is this month."""
    if not template.months:
        return None
    return min((month - today.month) % 12 for month in template.months)


def upcoming(today: date) -> list[FestivalTemplate]:
    """Every template, the soonest first; one without months last; ties by key."""
    return sorted(
        TEMPLATES,
        key=lambda t: (
            months_until(t, today) is None,
            months_until(t, today) or 0,
            t.key,
        ),
    )
