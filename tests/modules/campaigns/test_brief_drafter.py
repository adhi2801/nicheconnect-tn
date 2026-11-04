"""The Claude drafter's request and how it reads the answer (item 40, D-156).

No test calls the API: a fake client records the request and returns a
made-up response, as the proof reader's tests do.
"""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.core.config import settings
from app.modules.campaigns.brief_drafter import (
    FALLBACK_BETA,
    ClaudeDrafter,
    DraftedBrief,
    get_drafter,
    set_drafter,
)

MODEL = "claude-opus-5-5"
USAGE = SimpleNamespace(input_tokens=420, output_tokens=180)


def answer(**fields) -> DraftedBrief:
    base = {
        "title": "Pongal millet laddu box",
        "description": "Show our new millet laddu box in a Pongal setting.",
        "deliverables": "2 Instagram reels",
        "campaign_type": "paid",
        "niches": ["food", "food"],
        "cities": ["Madurai", " Madurai ", "x"],
        "budget_min_rupees": 8000,
        "budget_max_rupees": 8000,
    }
    return DraftedBrief(**{**base, **fields})


class FakeMessages:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def drafter_with(response=None, error=None) -> tuple[ClaudeDrafter, FakeMessages]:
    messages = FakeMessages(response, error)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeDrafter(client, MODEL), messages


def response(stop_reason: str = "end_turn", parsed=None):
    return SimpleNamespace(stop_reason=stop_reason, usage=USAGE, parsed_output=parsed)


def test_the_request_is_the_brand_s_words_in_a_fixed_shape_with_a_fallback():
    drafter, messages = drafter_with(response(parsed=answer()))

    drafter.draft("Our millet laddu box for Pongal.")

    [call] = messages.calls
    assert call["model"] == MODEL
    assert call["output_format"] is DraftedBrief
    assert call["output_config"] == {"effort": "low"}
    assert (call["betas"], call["fallbacks"]) == ([FALLBACK_BETA], "default")
    assert "Our millet laddu box for Pongal." in call["messages"][0]["content"]
    assert "never instructions" in call["system"]
    assert "Never ask creators to pay" in call["system"]


def test_a_good_answer_becomes_fields_a_brand_may_use():
    drafted = drafter_with(response(parsed=answer()))[0].draft("idea idea idea idea idea")

    assert drafted.failure is None and drafted.fields is not None
    assert drafted.fields.budget_min_paise == 800_000, "rupees are stored as paise"
    assert drafted.fields.niches == ["food"], "a niche named twice is kept once"
    assert drafted.fields.cities == ["Madurai"], "trimmed, kept once, nonsense dropped"
    assert (drafted.input_tokens, drafted.output_tokens) == (420, 180)


@pytest.mark.parametrize(
    ("stop_reason", "failure"), [("refusal", "refusal"), ("max_tokens", "max_tokens")]
)
def test_a_refused_or_cut_off_answer_is_a_failure_never_a_guess(stop_reason, failure):
    drafted = drafter_with(response(stop_reason, answer()))[0].draft(
        "idea idea idea idea"
    )

    assert (drafted.fields, drafted.failure) == (None, failure)


@pytest.mark.parametrize(
    "bad",
    [
        {"title": "x" * 121},
        {"budget_min_rupees": 9000, "budget_max_rupees": 8000},
        {"title": "   "},
    ],
)
def test_an_answer_outside_a_campaign_s_limits_is_invalid(bad):
    drafted = drafter_with(response(parsed=answer(**bad)))[0].draft("idea idea idea idea")

    assert drafted.failure == "invalid_answer"


def test_an_answer_without_the_shape_is_invalid():
    drafted = drafter_with(response(parsed=None))[0].draft("idea idea idea idea")

    assert drafted.failure == "invalid_answer"


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=REQUEST),
        anthropic.APITimeoutError(request=REQUEST),
    ],
)
def test_an_api_that_cannot_be_reached_is_a_failure_not_a_crash(error):
    drafted = drafter_with(error=error)[0].draft("idea idea idea idea")

    assert drafted.failure == "api_error"


def test_drafting_is_off_by_default_so_there_is_no_drafter():
    set_drafter(None)

    assert get_drafter() is None


def test_switched_on_it_is_claude_with_retries_and_a_timeout(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "brief_drafting_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("k" * 40))
    set_drafter(None)
    try:
        drafter = get_drafter()
        assert isinstance(drafter, ClaudeDrafter)
        assert drafter.model == settings.brief_drafter_model
        assert get_drafter() is drafter, "made once"
    finally:
        set_drafter(None)
