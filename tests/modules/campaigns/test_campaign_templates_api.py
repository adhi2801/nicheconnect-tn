"""Festival campaign templates (item 14, piece 1, D-161).

The rules worth proving: every template, with a city and a budget added, is
a campaign the real create route accepts and the text flags pass; the list
starts with the soonest, wrapping round the year, and a festival with no
months comes last; months are real months and keys are unique; it needs no
login, is cached for a day and is rate limited.
"""

from datetime import UTC, date, datetime

import pytest

from app.core.text_flags import flags_in
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import festival_templates
from app.modules.campaigns.festival_templates import TEMPLATES, months_until, upcoming
from app.modules.campaigns.template_router import PUBLIC_READ_LIMIT
from tests.deal_flow import CAMPAIGNS_URL, brand_user

URL = "/api/v1/campaign-templates"


def test_every_template_is_a_campaign_the_create_route_accepts(client, db, clock):
    brand = brand_user(db, clock)
    templates = client.get(URL).json()
    assert len(templates) == len(TEMPLATES) > 5

    for template in templates:
        body = {
            **template["campaign"],
            "cities": ["Madurai"],
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
        }
        made = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers)
        assert made.status_code == 201, (template["key"], made.text)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_no_template_asks_creators_for_money_or_contact_details(template):
    for text in (template.title, template.description, template.deliverables):
        assert flags_in(text, money=True, contact=True) == [], (template.key, text)


def test_months_are_real_and_keys_unique():
    assert len({t.key for t in TEMPLATES}) == len(TEMPLATES)
    for t in TEMPLATES:
        assert all(1 <= m <= 12 for m in t.months), t.key
        assert 1 <= t.lead_weeks <= 12, t.key


def test_the_soonest_comes_first_wrapping_round_the_year():
    in_november = [t.key for t in upcoming(date(2026, 11, 5))]
    in_february = [t.key for t in upcoming(date(2027, 2, 1))]

    assert in_november[:2] == ["deepavali", "karthigai_deepam"]
    assert in_february[0] == "puthandu"  # April is next; Pongal is ten months away
    assert in_february.index("pongal") > in_february.index("christmas")


def test_a_festival_that_follows_the_moon_is_listed_last_with_no_months():
    for today in (date(2026, 1, 1), date(2026, 7, 15), date(2026, 12, 31)):
        assert upcoming(today)[-1].key == "ramzan"
    ramzan = next(t for t in TEMPLATES if t.key == "ramzan")
    assert ramzan.months == () and months_until(ramzan, date(2026, 1, 1)) is None


def test_a_festival_this_month_is_zero_months_away():
    pongal = next(t for t in TEMPLATES if t.key == "pongal")
    assert months_until(pongal, date(2027, 1, 20)) == 0
    assert months_until(pongal, date(2026, 12, 31)) == 1


def test_the_route_orders_from_today_in_tamil_nadu(client):
    from app.main import app

    # 31 December, 20:00 in UTC, is already 1 January in Tamil Nadu: Pongal's month.
    app.dependency_overrides[get_now] = lambda: datetime(2026, 12, 31, 20, 0, tzinfo=UTC)
    try:
        first = client.get(URL).json()[0]["key"]
    finally:
        app.dependency_overrides.pop(get_now, None)

    assert first in {"pongal", "margazhi"}
    assert first == festival_templates.upcoming(date(2027, 1, 1))[0].key


def test_it_needs_no_login_and_is_cached_for_a_day(client):
    response = client.get(URL)

    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "public, max-age=86400"
    assert set(response.json()[0]) == {
        "key",
        "name",
        "when",
        "months",
        "lead_weeks",
        "campaign",
    }


def test_it_is_rate_limited(client):
    for _ in range(int(PUBLIC_READ_LIMIT.split()[0])):
        assert client.get(URL).status_code == 200
    assert client.get(URL).status_code == 429
