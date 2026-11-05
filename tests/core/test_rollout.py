"""A feature reaching a share of accounts first (item 92, D-160).

The rules worth proving: nobody flickers out as the share grows; 0 reaches
nobody and 100 everyone; the share is honest (10% is about a tenth); features
pick their first accounts independently; a share on a feature that ignores it,
or outside 0 to 100, stops the app starting; the public answer never says
"on" for a feature only some have; each account is told its own answer, a
team member as their brand; and the brief route refuses a brand outside the
share with the code it uses when drafting is off.
"""

import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core import features, rollout
from app.core.config import ROLLOUT_FEATURES, Settings, settings

ids = st.uuids()
percents = st.integers(0, 100)


@pytest.fixture
def share(monkeypatch):
    def set_to(percent: int, feature: str = "brief_drafting") -> None:
        monkeypatch.setattr(settings, "feature_rollout", {feature: percent})

    return set_to


@given(ids, percents, percents)
def test_an_account_in_at_one_share_is_in_at_every_larger_one(account, a, b):
    low, high = sorted((a, b))
    bucket = rollout.bucket("brief_drafting", account)
    assert 0 <= bucket < rollout.BUCKETS
    assert (bucket < low) <= (bucket < high)


def test_nought_reaches_nobody_and_a_hundred_everyone(monkeypatch):
    accounts = [uuid.UUID(int=n * 31 + 5) for n in range(500)]
    monkeypatch.setattr(settings, "feature_rollout", {"brief_drafting": 0})
    assert not any(rollout.includes("brief_drafting", a) for a in accounts)
    monkeypatch.setattr(settings, "feature_rollout", {"brief_drafting": 100})
    assert all(rollout.includes("brief_drafting", a) for a in accounts)


def test_a_tenth_is_about_a_tenth():
    """10,000 accounts at 10%: within 2 points, which a fair bucket misses
    about once in ten billion runs."""
    accounts = [uuid.UUID(int=n * 7919 + 1) for n in range(10_000)]
    reached = sum(rollout.bucket("brief_drafting", a) < 10 for a in accounts)
    assert 800 <= reached <= 1_200


def test_each_feature_picks_its_first_accounts_on_its_own():
    accounts = [uuid.UUID(int=n * 104_729 + 3) for n in range(2_000)]
    first = {a for a in accounts if rollout.bucket("brief_drafting", a) < 10}
    other = {a for a in accounts if rollout.bucket("connected_accounts", a) < 10}
    # Independent tenths overlap in about a hundredth: 20 of 2,000.
    assert len(first & other) < 60


def test_the_bucket_is_keyed_by_the_app_s_secret(monkeypatch):
    accounts = [uuid.UUID(int=n + 1) for n in range(200)]
    before = [rollout.bucket("brief_drafting", a) for a in accounts]
    monkeypatch.setattr(settings, "secret_key", type(settings.secret_key)("x" * 40))
    after = [rollout.bucket("brief_drafting", a) for a in accounts]
    assert before != after


def test_unset_means_everyone():
    assert rollout.share("brief_drafting") == 100


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"passkeys": 10}, "only brief_drafting honour a share"),
        ({"brief_drafting": 101}, "not 0 to 100"),
        ({"brief_drafting": -1}, "not 0 to 100"),
    ],
)
def test_a_share_that_could_not_be_honoured_stops_the_app_starting(value, message):
    with pytest.raises(ValidationError, match=message):
        Settings(**{**settings.model_dump(), "feature_rollout": value})


def test_every_feature_that_honours_a_share_is_a_feature_screens_are_told_of():
    assert set(ROLLOUT_FEATURES) <= set(features.FeaturesRead.model_fields)


def test_the_public_answer_says_off_and_gives_the_share_while_only_some_have_it(
    share, monkeypatch
):
    monkeypatch.setattr(settings, "brief_drafting_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", type(settings.secret_key)("k"))
    share(10)

    found = features.current().brief_drafting

    assert (found.on, found.share_percent) == (False, 10)
    share(100)
    assert features.current().brief_drafting.on is True
