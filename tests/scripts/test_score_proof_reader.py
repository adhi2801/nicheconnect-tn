"""The script that picks the proof reader's model by measurement (D-070, step 2).

Fake readers stand in for Claude, so these tests cost nothing and check the
scoring itself: a made-up number counts against a model, a missed one too,
an abbreviated one is judged as the screen shows it, and nothing is sent
without --spend.
"""

import json
import pathlib
from datetime import date

import pytest

from app.modules.deal_memo.proof_reader import PROMPT_VERSION, Reading
from scripts import score_proof_reader as scorer

TRUTH = {"views": 48210, "reach": 31400, "likes": 2104}


def read(
    numbers=None,
    status="read",
    abbreviated=(),
    handle="priya.eats",
    post_date=date(2026, 9, 28),
    failure=None,
):
    return Reading(
        status=status,
        model="m",
        prompt_version=PROMPT_VERSION,
        numbers=numbers,
        platform="instagram",
        handle=handle,
        post_date=post_date,
        abbreviated=tuple(abbreviated),
        failure=failure,
        input_tokens=4000,
        output_tokens=500,
    )


class FakeReader:
    def __init__(self, readings: dict[str, Reading]) -> None:
        self.readings = readings
        self.calls: list[int] = []

    def read(self, image: bytes, content_type: str) -> Reading:
        self.calls.append(len(image))
        return self.readings[image.decode()]


def make_set(folder: pathlib.Path, answers: dict) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in answers:
        # The "image" holds its own name, so the fake reader knows which it is.
        (folder / name).write_bytes(name.encode())
    (folder / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    return folder


def insights(**numbers):
    return {
        "platform": "instagram",
        "handle": "@Priya.Eats",
        "post_date": "2026-09-28",
        "numbers": numbers or TRUTH,
    }


def run(folder, readings_by_model, *extra):
    lines: list[str] = []
    readers = {model: FakeReader(r) for model, r in readings_by_model.items()}
    code = scorer.main(
        [str(folder), "--models", *readings_by_model, *extra],
        reader_for=lambda model: readers[model],
        out=lines.append,
    )
    return code, "\n".join(lines), readers


def expected(raw=None):
    return scorer.parse_expected("a.png", raw if raw is not None else insights())


# --- scoring ------------------------------------------------------------------------------


def test_every_number_right_passes():
    score = scorer.Score(model="claude-haiku-4-5")

    scorer.score_one(score, "a.png", expected(), read(TRUTH))

    assert (score.right, score.missed, score.wrong, score.invented) == (3, 0, 0, 0)
    assert score.passes


def test_a_made_up_number_fails_the_model():
    score = scorer.Score(model="m")

    scorer.score_one(score, "a.png", expected(), read({**TRUTH, "saves": 9}))

    assert score.invented == 1
    assert not score.passes
    assert "saves 9 is not on the screen" in score.mistakes[0]


def test_a_missed_and_a_wrong_number_both_count():
    score = scorer.Score(model="m")

    scorer.score_one(score, "a.png", expected(), read({"views": 48201, "reach": 31400}))

    assert (score.right, score.missed, score.wrong) == (1, 1, 1)


def test_an_abbreviated_number_is_right_when_it_rounds_to_the_screen():
    score = scorer.Score(model="m")
    truth = expected(insights(views=12500))

    scorer.score_one(score, "a.png", truth, read({"views": 12480}, abbreviated=["views"]))
    scorer.score_one(score, "b.png", truth, read({"views": 13500}, abbreviated=["views"]))

    assert (score.right, score.wrong) == (1, 1)


def test_numbers_read_off_a_screen_with_none_are_made_up():
    score = scorer.Score(model="m")

    scorer.score_one(score, "a.png", expected({"insights": False}), read(TRUTH))

    assert score.screens_misjudged == 1
    assert score.invented == 3


def test_no_numbers_found_on_an_insights_screen_misses_them_all():
    score = scorer.Score(model="m")

    scorer.score_one(score, "a.png", expected(), read(status="no_numbers"))

    assert (score.missed, score.screens_misjudged) == (3, 1)


def test_a_failed_reading_fails_the_model_and_still_costs():
    score = scorer.Score(model="claude-opus-5-5")

    scorer.score_one(
        score, "a.png", expected(), read(status="failed", failure="api_error")
    )

    assert score.failures == 1
    assert not score.passes
    assert score.dollars == pytest.approx((4000 * 4 + 500 * 20) / 1_000_000)


def test_a_wrong_handle_or_date_is_reported():
    score = scorer.Score(model="m")

    scorer.score_one(
        score,
        "a.png",
        expected(),
        read(TRUTH, handle="someone.else", post_date=date(2026, 9, 1)),
    )

    assert (score.handles_wrong, score.dates_wrong) == (1, 1)


# --- the run ------------------------------------------------------------------------------


def test_without_spend_nothing_is_sent_and_the_ceiling_is_printed(tmp_path):
    folder = make_set(tmp_path / "set", {"a.png": insights()})

    code, output, readers = run(folder, {"claude-opus-5-5": {}})

    assert code == 0
    assert "Nothing sent" in output
    assert "At most $" in output
    assert readers["claude-opus-5-5"].calls == []


def test_with_spend_the_cheapest_model_that_reads_everything_right_is_named(tmp_path):
    folder = make_set(
        tmp_path / "set", {"a.png": insights(), "b.png": {"insights": False}}
    )
    perfect = {"a.png": read(TRUTH), "b.png": read(status="no_numbers")}
    sloppy = {"a.png": read({**TRUTH, "saves": 1}), "b.png": read(status="no_numbers")}

    code, output, _ = run(
        folder,
        {
            "claude-opus-5-5": perfect,
            "claude-sonnet-5-5": perfect,
            "claude-haiku-4-5": sloppy,
        },
        "--spend",
    )

    assert code == 0
    assert "Cheapest model that read everything right: claude-sonnet-5-5" in output
    assert "saves 1 is not on the screen" in output


def test_when_no_model_passes_it_says_so(tmp_path):
    folder = make_set(tmp_path / "set", {"a.png": insights()})

    _, output, _ = run(
        folder, {"claude-haiku-4-5": {"a.png": read({"views": 1})}}, "--spend"
    )

    assert "No model read everything right" in output


# --- a test set that cannot be used -------------------------------------------------------


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"a.png": insights(), "ghost.png": insights()}, "not there"),
        ({"a.png": {"platform": "instagram"}}, "needs its numbers"),
        ({"a.png": insights(followers=10)}, "unknown metrics"),
        ({"a.png": insights(views=-1)}, "whole number"),
        ({"a.png": {**insights(), "post_date": "28/09/2026"}}, "YYYY-MM-DD"),
    ],
)
def test_a_broken_answer_file_is_refused_with_the_reason(tmp_path, answers, message):
    folder = tmp_path / "set"
    folder.mkdir()
    (folder / "a.png").write_bytes(b"a.png")
    (folder / "answers.json").write_text(json.dumps(answers), encoding="utf-8")

    code, output, _ = run(folder, {"claude-opus-5-5": {}})

    assert code == 2
    assert message in output


def test_a_screenshot_without_an_answer_is_refused(tmp_path):
    folder = make_set(tmp_path / "set", {"a.png": insights()})
    (folder / "extra.png").write_bytes(b"x")

    code, output, _ = run(folder, {"claude-opus-5-5": {}})

    assert code == 2
    assert "no answer for: extra.png" in output


def test_a_missing_folder_is_refused(tmp_path):
    code, output, _ = run(tmp_path / "nowhere", {"claude-opus-5-5": {}})

    assert code == 2
    assert "answers.json not found" in output


def test_a_model_without_a_price_is_refused(tmp_path):
    folder = make_set(tmp_path / "set", {"a.png": insights()})

    code, output, _ = run(folder, {"claude-unknown-9": {}})

    assert code == 2
    assert "No price known" in output


def test_without_a_key_the_real_reader_refuses(monkeypatch):
    monkeypatch.setattr(scorer.settings, "anthropic_api_key", None)

    with pytest.raises(scorer.TestSetError, match="ANTHROPIC_API_KEY"):
        scorer.claude_reader("claude-opus-5-5")
