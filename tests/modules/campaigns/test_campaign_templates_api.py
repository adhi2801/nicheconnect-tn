"""Festival campaign templates (item 14, piece 1, D-161, D-165).

The rules worth proving: every template, with a city and a budget added, is a
campaign the real create route accepts and the text flags pass; the list is
ordered only by date, the one to publish soonest first, so no faith is placed
by its faith; a festival that is over moves to its next year; the dates are
the sourced ones and reach a year ahead on the real calendar; the response
carries each template's own values; it needs no login, is cached until
midnight in Tamil Nadu with an ETag and a 304, and is rate limited.
"""

import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import IST, india_date
from app.core.text_flags import flags_in
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import festival_templates
from app.modules.campaigns.festival_templates import (
    DATED,
    LABEL,
    TEMPLATES,
    easter_sunday,
    next_occurrence,
    publish_by,
    upcoming,
)
from app.modules.campaigns.template_router import (
    PUBLIC_READ_LIMIT,
    seconds_to_india_midnight,
)
from tests.deal_flow import CAMPAIGNS_URL, brand_user

URL = "/api/v1/campaign-templates"
KEYS = {
    "new_year", "pongal", "puthandu", "easter", "ramzan", "bakrid", "back_to_school", "aadi",
    "independence_day", "velankanni", "vinayagar_chathurthi", "navaratri", "deepavali",
    "karthigai_deepam", "margazhi", "christmas",
}  # fmt: skip
# The dates the table is written for: from today's build to the end of its last year.
COVERED = st.dates(min_value=date(2026, 11, 6), max_value=date(2027, 12, 31))


def keys_on(day: date) -> list[str]:
    return [t.key for t, _ in upcoming(day)]


def at(moment: datetime):
    from app.main import app

    app.dependency_overrides[get_now] = lambda: moment
    return app


# --- the templates themselves -------------------------------------------------------


def test_the_keys_are_pinned_so_a_link_never_breaks():
    assert {t.key for t in TEMPLATES} == KEYS
    assert len(TEMPLATES) == len(KEYS)


def test_every_template_is_a_campaign_the_create_route_accepts(client, db, clock):
    templates = client.get(URL).json()
    assert {t["key"] for t in templates} == KEYS

    # a brand may create 20 campaigns a day, so a fresh one for each batch of 15
    for i, template in enumerate(templates):
        if i % 15 == 0:
            brand = brand_user(db, clock)
        body = {
            **template["campaign"],
            "cities": ["Madurai"],
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
        }
        made = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers)
        assert made.status_code == 201, (template["key"], made.text)
        assert (
            made.json()["deliverable_items"] == template["campaign"]["deliverable_items"]
        )


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_no_template_asks_for_money_or_contact_and_every_one_asks_for_the_label(template):
    for text in (template.title, template.description, template.deliverables):
        assert flags_in(text, money=True, contact=True) == [], (template.key, text)
    assert template.deliverables.endswith(LABEL)
    assert 1 <= template.lead_weeks <= 12


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_the_deliverables_text_and_list_say_the_same(template):
    stem = {"reel": "reel", "story": "stor"}
    for item in template.items:
        said = rf"\b{item.quantity} (Instagram )?{stem[item.format]}"
        assert re.search(said, template.deliverables), (template.key, item)
    assert {i.format for i in template.items} <= set(stem)


def test_no_template_stages_a_deity_or_worship():
    # TAMIL_DESIGN_ROOTS.md rule 1: festivals as people keep them at home, never worship
    for t in TEMPLATES:
        text = f"{t.title} {t.description}".lower()
        for word in (
            "idol",
            "god",
            "goddess",
            "puja",
            "prayer",
            "church",
            "mosque",
            "temple",
        ):
            assert word not in text.split(), (t.key, word)


# --- the dates ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "easter"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)),
     (2027, date(2027, 3, 28)), (2028, date(2028, 4, 16)), (2038, date(2038, 4, 25))],
)  # fmt: skip
def test_easter_by_the_church_s_rule(year, easter):
    assert easter_sunday(year) == easter
    # the Government's 2027 list has Good Friday on 26 March: two days before
    assert easter_sunday(2027) - timedelta(days=2) == date(2027, 3, 26)


def test_the_notified_days_are_the_government_s():
    # G.O. 2026 and G.O. (Ms.) No. 613 for 2027, as recorded in festival_templates.py
    notified = {
        "deepavali": [date(2026, 11, 8), date(2027, 10, 28)],
        "vinayagar_chathurthi": [date(2027, 9, 4)],
        "bakrid": [date(2027, 5, 17)],
    }
    for key, days in notified.items():
        starts = {o.starts_on for o in DATED[key]}
        assert set(days) <= starts, key
    assert DATED["ramzan"][0].ends_on == date(2027, 3, 10)  # Eid ul-Fitr 2027
    assert date(2027, 1, 15) in _days(DATED["pongal"][0])


def _days(o):
    return {
        o.starts_on + timedelta(days=i) for i in range((o.ends_on - o.starts_on).days + 1)
    }


def test_a_moon_sighted_day_is_never_confirmed_ahead():
    for key in ("ramzan", "bakrid"):
        t = next(t for t in TEMPLATES if t.key == key)
        assert t.moon
        assert not any(o.confirmed for o in DATED[key])


def test_the_dates_reach_a_year_ahead():
    """Fails on the real calendar once the table runs short: add the next year's dates
    when the Government notifies them (about October each year)."""
    today = india_date(datetime.now(UTC))
    for day in (today, today + timedelta(days=300)):
        missing = [t.key for t in TEMPLATES if next_occurrence(t, day) is None]
        assert missing == [], (day, missing)


# --- the order ----------------------------------------------------------------------


def test_on_25_november_what_is_over_has_moved_to_next_year():
    order = keys_on(date(2026, 11, 25))
    by_key = {t.key: o for t, o in upcoming(date(2026, 11, 25))}

    assert by_key["deepavali"].starts_on == date(2027, 10, 28)
    assert by_key["karthigai_deepam"].starts_on == date(2027, 12, 12)
    # Margazhi's and Christmas's publish-by days are before Pongal's, and all three before
    # the festivals that are a year away
    assert order.index("margazhi") < order.index("christmas") < order.index("pongal")
    assert order.index("pongal") < order.index("deepavali")


def test_on_20_january_pongal_is_over_and_the_next_is_puthandu_s_season():
    by_key = {t.key: o for t, o in upcoming(date(2027, 1, 20))}
    assert by_key["pongal"].starts_on == date(2028, 1, 14)
    assert by_key["margazhi"].starts_on == date(2027, 12, 16)
    # Ramzan (Eid 10 March 2027) is to be published before Easter and Puthandu
    order = keys_on(date(2027, 1, 20))
    assert order.index("ramzan") < order.index("easter") < order.index("puthandu")


def test_on_26_december_christmas_is_next_year_s():
    by_key = {t.key: o for t, o in upcoming(date(2026, 12, 26))}
    assert by_key["christmas"].starts_on == date(2027, 12, 24)
    assert keys_on(date(2026, 12, 26))[-1] != "ramzan"


def test_one_under_way_leads_the_list():
    # 30 December: Margazhi is under way; New Year's Eve is a day away
    order = keys_on(date(2026, 12, 30))
    assert order[:2] == ["margazhi", "new_year"]


def test_ties_are_broken_by_key_not_by_the_list_s_order(monkeypatch):
    t = next(t for t in TEMPLATES if t.key == "christmas")
    twins = (replace(t, key="zz_second"), replace(t, key="aa_first"))
    monkeypatch.setattr(festival_templates, "TEMPLATES", twins)
    assert keys_on(date(2026, 11, 6)) == ["aa_first", "zz_second"]


def test_a_template_the_table_no_longer_reaches_is_left_out_not_guessed(monkeypatch):
    monkeypatch.setitem(festival_templates.DATED, "bakrid", ())
    assert "bakrid" not in keys_on(date(2026, 11, 6))


@given(COVERED)
def test_for_any_day_every_template_comes_once_in_date_order(day):
    found = upcoming(day)
    assert sorted(t.key for t, _ in found) == sorted(KEYS)
    keys = [(publish_by(t, o), o.starts_on, t.key) for t, o in found]
    assert keys == sorted(keys)
    for _, o in found:
        assert o.ends_on >= day  # nothing that is over
        assert o.starts_on <= o.ends_on


@given(COVERED)
def test_for_any_day_the_occurrence_is_the_first_not_over(day):
    for t, o in upcoming(day):
        earlier = [
            x for x in festival_templates.occurrences(t, day) if x.starts_on < o.starts_on
        ]
        assert all(x.ends_on < day for x in earlier), t.key


# --- the route ----------------------------------------------------------------------


def test_the_response_carries_each_template_s_own_values(client):
    app = at(datetime(2026, 11, 6, 6, 0, tzinfo=UTC))
    try:
        body = client.get(URL).json()
    finally:
        app.dependency_overrides.pop(get_now, None)

    for row, (t, o) in zip(body, upcoming(date(2026, 11, 6)), strict=True):
        assert row["key"] == t.key
        assert row["name"] == t.name
        assert row["when"] == t.when
        assert row["lead_weeks"] == t.lead_weeks
        assert row["starts_on"] == o.starts_on.isoformat()
        assert row["ends_on"] == o.ends_on.isoformat()
        assert (
            row["publish_by"] == (o.starts_on - timedelta(weeks=t.lead_weeks)).isoformat()
        )
        assert row["dates_confirmed"] is o.confirmed
        assert row["depends_on_moon"] is t.moon
        assert row["campaign"]["title"] == t.title
        assert row["campaign"]["niches"] == list(t.niches)
        assert len(row["campaign"]["deliverable_items"]) == len(t.items)


def test_the_route_reads_today_in_tamil_nadu(client):
    # 1 January 2027, 18:40 in UTC, is already 2 January in Tamil Nadu: New Year is over
    app = at(datetime(2027, 1, 1, 18, 40, tzinfo=UTC))
    try:
        rows = {r["key"]: r for r in client.get(URL).json()}
    finally:
        app.dependency_overrides.pop(get_now, None)

    assert rows["new_year"]["starts_on"] == "2027-12-31"


def test_it_needs_no_login_and_is_cached_until_midnight_with_an_etag(client):
    app = at(datetime(2026, 11, 6, 18, 0, tzinfo=IST))
    try:
        first = client.get(URL)
        again = client.get(URL, headers={"If-None-Match": first.headers["ETag"]})
        stale = client.get(URL, headers={"If-None-Match": '"not-this-one"'})
    finally:
        app.dependency_overrides.pop(get_now, None)

    assert first.status_code == 200, first.text
    assert (
        first.headers["Cache-Control"] == "public, max-age=21600"
    )  # six hours to midnight
    assert again.status_code == 304
    assert again.headers["ETag"] == first.headers["ETag"]
    assert stale.status_code == 200


def test_a_new_day_s_order_is_a_new_etag(client):
    tags = []
    for moment in (
        datetime(2026, 11, 24, 12, 0, tzinfo=IST),
        datetime(2026, 11, 25, 12, 0, tzinfo=IST),
    ):
        app = at(moment)
        try:
            tags.append(client.get(URL).headers["ETag"])
        finally:
            app.dependency_overrides.pop(get_now, None)
    assert tags[0] != tags[1]  # Karthigai Deepam (24 November 2026) is over on the 25th


def test_the_cache_never_drops_below_a_minute():
    just_before = datetime(2026, 11, 6, 23, 59, 50, tzinfo=IST)
    assert seconds_to_india_midnight(just_before) == 60
    assert seconds_to_india_midnight(datetime(2026, 11, 6, 0, 0, tzinfo=IST)) == 86_400


def test_it_is_rate_limited(client):
    for _ in range(int(PUBLIC_READ_LIMIT.split()[0])):
        assert client.get(URL).status_code == 200
    assert client.get(URL).status_code == 429


def test_a_template_may_ask_for_stories_alone():
    assert festival_templates.reels_and_stories(0, 2) == (
        festival_templates.Item("instagram", "story", 2),
    )
