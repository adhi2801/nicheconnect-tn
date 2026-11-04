"""A campaign brief drafted from a brand's own words (item 40, D-156).

The rules worth proving: the request stores the words and returns at once,
the job drafts them out of the request; a brand reads only its own drafts;
only roles that run campaigns may ask; three may wait per brand; a refusal or
an answer that does not fit is final, a failed call is tried three times; the
day's ceiling stops the job; a week later the draft is gone; switched off, it
says so. No test calls the API: a fake drafter stands in.
"""

from datetime import timedelta

import pytest

from app.modules.campaigns import brief_service
from app.modules.campaigns.brief_drafter import BriefFields, Drafted, set_drafter
from tests.deal_flow import brand_user, creator_user
from tests.modules.me.test_team_api import join

URL = "/api/v1/brief-drafts"
IDEA = "Our new millet laddu box for Pongal. Two reels from Madurai food creators, Rs 8,000 each."
FIELDS = BriefFields(
    title="Pongal millet laddu box",
    description="Show our new millet laddu box in a Pongal setting.",
    deliverables="2 Instagram reels",
    campaign_type="paid",
    niches=["food"],
    cities=["Madurai"],
    budget_min_paise=800_000,
    budget_max_paise=800_000,
)


class FakeDrafter:
    def __init__(self, *answers: Drafted) -> None:
        self.answers = list(answers)
        self.ideas: list[str] = []

    def draft(self, idea: str) -> Drafted:
        self.ideas.append(idea)
        return self.answers.pop(0) if self.answers else Drafted(FIELDS, None, "fake")


@pytest.fixture
def drafter():
    fake = FakeDrafter()
    set_drafter(fake)
    yield fake
    set_drafter(None)


def ask(client, user, idea: str = IDEA):
    return client.post(URL, json={"idea": idea}, headers=user.headers)


def problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def test_the_words_wait_and_the_job_drafts_them(client, db, clock, drafter):
    brand = brand_user(db, clock)

    asked = ask(client, brand)

    assert asked.status_code == 202, asked.text
    assert asked.json()["status"] == "waiting" and asked.json()["draft"] is None
    assert asked.headers["Location"] == f"{URL}/{asked.json()['id']}"
    assert drafter.ideas == [], "nothing is drafted inside the request"
    run = brief_service.run(db, drafter, clock.now)
    assert run.drafted == 1
    ready = client.get(asked.headers["Location"], headers=brand.headers).json()
    assert ready["status"] == "ready"
    assert ready["draft"]["title"] == "Pongal millet laddu box"
    assert ready["draft"]["budget_min_paise"] == 800_000
    assert drafter.ideas == [IDEA]


def test_a_brand_reads_only_its_own_drafts(client, db, clock, drafter):
    mine = ask(client, brand_user(db, clock)).json()["id"]

    problem(
        client.get(f"{URL}/{mine}", headers=brand_user(db, clock).headers),
        404,
        "brief_draft_not_found",
    )


def test_finance_reads_a_draft_but_never_asks_for_one(client, db, clock, drafter):
    owner = brand_user(db, clock)
    finance = join(client, db, clock, owner, "finance")
    campaigns = join(client, db, clock, owner, "campaigns", "Kavi")

    problem(ask(client, finance), 403, "brand_role_not_allowed")
    made = ask(client, campaigns)
    assert made.status_code == 202, made.text
    assert (
        client.get(f"{URL}/{made.json()['id']}", headers=finance.headers).status_code
        == 200
    )


def test_a_creator_has_no_drafts(client, db, clock, drafter):
    problem(ask(client, creator_user(db, clock)), 403, "role_not_allowed")


def test_three_wait_at_most_per_brand(client, db, clock, drafter):
    brand = brand_user(db, clock)
    for _ in range(3):
        assert ask(client, brand).status_code == 202

    problem(ask(client, brand), 409, "brief_drafts_waiting")
    brief_service.run(db, drafter, clock.now)
    assert ask(client, brand).status_code == 202


@pytest.mark.parametrize("idea", ["too short", "x" * 1501])
def test_the_words_must_be_a_few_sentences(client, db, clock, drafter, idea):
    assert ask(client, brand_user(db, clock), idea).status_code == 422


@pytest.mark.parametrize("failure", ["refusal", "invalid_answer"])
def test_a_refusal_or_an_answer_out_of_shape_is_final(client, db, clock, failure):
    fake = FakeDrafter(Drafted(None, failure, "fake"))
    set_drafter(fake)
    try:
        brand = brand_user(db, clock)
        made = ask(client, brand).json()["id"]
        brief_service.run(db, fake, clock.now)
        shown = client.get(f"{URL}/{made}", headers=brand.headers).json()
        assert (shown["status"], shown["failure"]) == ("failed", failure)
    finally:
        set_drafter(None)


def test_a_failed_call_is_tried_three_times(client, db, clock):
    fake = FakeDrafter(*[Drafted(None, "api_error", "fake")] * 3)
    set_drafter(fake)
    try:
        brand = brand_user(db, clock)
        made = ask(client, brand).json()["id"]
        statuses = []
        for _ in range(3):
            brief_service.run(db, fake, clock.now)
            statuses.append(
                client.get(f"{URL}/{made}", headers=brand.headers).json()["status"]
            )
        assert statuses == ["waiting", "waiting", "failed"]
    finally:
        set_drafter(None)


def test_the_day_s_ceiling_stops_the_job(client, db, clock, drafter, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "brief_drafting_daily_limit", 1)
    brand = brand_user(db, clock)
    ask(client, brand)
    ask(client, brand)

    first = brief_service.run(db, drafter, clock.now)
    second = brief_service.run(db, drafter, clock.now)

    assert (first.drafted, second.drafted, second.stopped_at_limit) == (1, 0, True)
    clock.advance(timedelta(days=1, seconds=1))
    assert brief_service.run(db, drafter, clock.now).drafted == 1


def test_a_draft_is_gone_after_a_week(client, db, clock, drafter):
    brand = brand_user(db, clock)
    made = ask(client, brand).json()["id"]
    brief_service.run(db, drafter, clock.now)
    clock.advance(timedelta(days=7, seconds=1))

    run = brief_service.run(db, drafter, clock.now)

    assert run.deleted >= 1
    problem(
        client.get(f"{URL}/{made}", headers=brand.headers), 404, "brief_draft_not_found"
    )


def test_switched_off_it_says_so(client, db, clock):
    set_drafter(None)

    problem(ask(client, brand_user(db, clock)), 503, "brief_drafting_unavailable")
    assert brief_service.run(db, None, clock.now).drafted == 0


def test_whoever_asked_finds_their_words_in_their_export(db, clock, drafter, client):
    brand = brand_user(db, clock)
    ask(client, brand)

    [section] = brief_service.export_for_account(db, brand.account_id)

    assert section.table == "campaign_brief_draft"
    assert IDEA in str(section)


def test_a_week_old_draft_is_not_read_even_before_the_job_deletes_it(
    client, db, clock, drafter
):
    """Two guards, each with its test: reading stops at a week whether or not the job has run."""
    brand = brand_user(db, clock)
    made = ask(client, brand).json()["id"]
    clock.advance(timedelta(days=7, seconds=1))

    problem(
        client.get(f"{URL}/{made}", headers=brand.headers), 404, "brief_draft_not_found"
    )
