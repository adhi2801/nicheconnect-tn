"""Score each Claude model on real proof screenshots, and price the run (D-070, step 2).

Decision 2 of D-070: the model that reads screenshots is chosen by measurement.
This reads every screenshot in a test set with each model, compares every
number with the true one written down beside it, and prints, per model,
what it got right, what it missed, what it got wrong, what it **made up**,
and what it cost.

A made-up number is the worst outcome: a missed one shows as empty, an
invented one misleads a brand. A model passes only with no wrong and no
invented number at all.

The test set is a folder that never enters git (`.gitignore` refuses
`local/`): screenshots of the founders' own posts, which are their business
data, and an `answers.json` beside them:

    {
      "reel-insights.png": {
        "platform": "instagram",
        "handle": "priya.eats",
        "post_date": "2026-09-28",
        "numbers": {"views": 48210, "reach": 31400, "likes": 2104}
      },
      "not-insights.jpg": {"insights": false}
    }

List only what the screen shows. A metric left out must come back empty.

Every run with --spend is real API calls that cost real money, about one to
three rupees per screenshot per model. Without --spend it only checks the set
and prints what the run would cost at most:

    uv run python scripts\\score_proof_reader.py local\\reader-test-set
    uv run python scripts\\score_proof_reader.py local\\reader-test-set --spend
"""

import argparse
import json
import pathlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.modules.deal_memo.proof_reader import (
    API_MAX_RETRIES,
    API_TIMEOUT_SECONDS,
    MAX_TOKENS,
    METRICS,
    ClaudeReader,
    Reading,
    ScreenshotReader,
)

DEFAULT_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5")
# Dollars per million tokens, input and output: Anthropic's published prices
# as of 25 September 2026. Used only to print what a run cost.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
# A ceiling for the dry run: no screenshot sends more than this in.
MAX_INPUT_TOKENS_PER_IMAGE = 6_000
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class TestSetError(ValueError):
    """The test set is missing, unreadable, or does not match its answers."""


@dataclass(frozen=True)
class Expected:
    insights: bool
    platform: str | None = None
    handle: str | None = None
    post_date: date | None = None
    numbers: dict[str, int] = field(default_factory=dict)


@dataclass
class Score:
    model: str
    screenshots: int = 0
    right: int = 0
    missed: int = 0
    wrong: int = 0
    invented: int = 0
    screens_misjudged: int = 0
    handles_wrong: int = 0
    dates_wrong: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    mistakes: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return (
            self.wrong == 0
            and self.invented == 0
            and self.missed == 0
            and self.screens_misjudged == 0
            and self.failures == 0
        )

    @property
    def dollars(self) -> float:
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000


def load_test_set(folder: pathlib.Path) -> list[tuple[pathlib.Path, Expected]]:
    """Every screenshot in the folder with its answer, or an error naming what is off."""
    answers_file = folder / "answers.json"
    if not answers_file.is_file():
        raise TestSetError(f"{answers_file} not found")
    try:
        answers = json.loads(answers_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TestSetError(f"answers.json is not valid JSON: {error}") from error
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_TYPES)
    if not images:
        raise TestSetError(f"no screenshots in {folder}")
    unanswered = [p.name for p in images if p.name not in answers]
    if unanswered:
        raise TestSetError(f"no answer for: {', '.join(unanswered)}")
    missing = sorted(set(answers) - {p.name for p in images})
    if missing:
        raise TestSetError(
            f"answers for screenshots that are not there: {', '.join(missing)}"
        )
    return [(image, parse_expected(image.name, answers[image.name])) for image in images]


def parse_expected(name: str, raw: dict[str, object]) -> Expected:
    if raw.get("insights") is False:
        return Expected(insights=False)
    numbers = raw.get("numbers") or {}
    if not isinstance(numbers, dict) or not numbers:
        raise TestSetError(f"{name}: an insights screen needs its numbers")
    unknown = sorted(set(numbers) - set(METRICS))
    if unknown:
        raise TestSetError(f"{name}: unknown metrics {unknown}; use {list(METRICS)}")
    if not all(isinstance(v, int) and v >= 0 for v in numbers.values()):
        raise TestSetError(f"{name}: every number must be a whole number, 0 or more")
    post_date = raw.get("post_date")
    try:
        parsed_date = date.fromisoformat(str(post_date)) if post_date else None
    except ValueError as error:
        raise TestSetError(f"{name}: post_date must be YYYY-MM-DD") from error
    return Expected(
        insights=True,
        platform=str(raw["platform"]) if raw.get("platform") else None,
        handle=str(raw["handle"]).lower().lstrip("@") if raw.get("handle") else None,
        post_date=parsed_date,
        numbers={str(k): int(v) for k, v in numbers.items()},
    )


def score_one(score: Score, name: str, expected: Expected, reading: Reading) -> None:
    """Add one screenshot's reading to the model's score."""
    score.screenshots += 1
    score.input_tokens += reading.input_tokens
    score.output_tokens += reading.output_tokens
    if reading.status == "failed":
        score.failures += 1
        score.mistakes.append(f"{name}: failed ({reading.failure})")
        return
    if not expected.insights:
        if reading.status == "read":
            score.screens_misjudged += 1
            score.invented += len(reading.numbers or {})
            score.mistakes.append(f"{name}: read numbers off a screen that has none")
        return
    if reading.status != "read":
        score.screens_misjudged += 1
        score.missed += len(expected.numbers)
        score.mistakes.append(f"{name}: found no numbers on an insights screen")
        return
    got = reading.numbers or {}
    for metric in METRICS:
        truth, read = expected.numbers.get(metric), got.get(metric)
        if truth is None and read is not None:
            score.invented += 1
            score.mistakes.append(f"{name}: {metric} {read} is not on the screen")
        elif truth is not None and read is None:
            score.missed += 1
            score.mistakes.append(f"{name}: {metric} missed (is {truth})")
        elif truth is not None and read != truth and metric not in reading.abbreviated:
            score.wrong += 1
            score.mistakes.append(f"{name}: {metric} read {read}, is {truth}")
        elif truth is not None:
            # An abbreviated number on screen (12.5K) cannot be exact: right
            # when it rounds back to what the screen shows.
            if metric in reading.abbreviated and not same_when_abbreviated(read, truth):
                score.wrong += 1
                score.mistakes.append(f"{name}: {metric} read {read}, is about {truth}")
            else:
                score.right += 1
    if expected.handle and reading.handle != expected.handle:
        score.handles_wrong += 1
        score.mistakes.append(
            f"{name}: handle read {reading.handle}, is {expected.handle}"
        )
    if expected.post_date and reading.post_date != expected.post_date:
        score.dates_wrong += 1
        score.mistakes.append(
            f"{name}: date read {reading.post_date}, is {expected.post_date}"
        )


def same_when_abbreviated(read: int | None, truth: int) -> bool:
    """12.5K stands for anything from 12,450 to 12,549: within 1% is the same."""
    return read is not None and abs(read - truth) <= max(1, truth // 100)


def claude_reader(model: str) -> ScreenshotReader:
    import anthropic

    if settings.anthropic_api_key is None:
        raise TestSetError("ANTHROPIC_API_KEY is not set in .env")
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=API_TIMEOUT_SECONDS,
        max_retries=API_MAX_RETRIES,
    )
    return ClaudeReader(client, model)


def report(scores: list[Score], out: Callable[[str], None]) -> None:
    out("")
    out(
        f"{'model':<20}{'right':>7}{'missed':>8}{'wrong':>7}{'made up':>9}"
        f"{'failed':>8}{'cost $':>9}{'per shot $':>12}  verdict"
    )
    for s in scores:
        per = s.dollars / s.screenshots if s.screenshots else 0.0
        verdict = "PASSES" if s.passes else "fails"
        out(
            f"{s.model:<20}{s.right:>7}{s.missed:>8}{s.wrong:>7}{s.invented:>9}"
            f"{s.failures:>8}{s.dollars:>9.4f}{per:>12.4f}  {verdict}"
        )
    for s in scores:
        for mistake in s.mistakes:
            out(f"  {s.model}: {mistake}")
    passing = sorted((s for s in scores if s.passes), key=lambda s: s.dollars)
    out("")
    if passing:
        out(f"Cheapest model that read everything right: {passing[0].model}")
    else:
        out(
            "No model read everything right. Keep Opus 5.5 and look at the mistakes above."
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    reader_for: Callable[[str], ScreenshotReader] = claude_reader,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=pathlib.Path)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument(
        "--spend", action="store_true", help="really call the API; it costs money"
    )
    args = parser.parse_args(argv)
    try:
        cases = load_test_set(args.folder)
    except TestSetError as error:
        out(f"Test set not usable: {error}")
        return 2
    unpriced = [m for m in args.models if m not in PRICES]
    if unpriced:
        out(f"No price known for {', '.join(unpriced)}; add it to PRICES first.")
        return 2

    ceiling = sum(
        len(cases)
        * (MAX_INPUT_TOKENS_PER_IMAGE * PRICES[m][0] + MAX_TOKENS * PRICES[m][1])
        / 1_000_000
        for m in args.models
    )
    out(
        f"{len(cases)} screenshots x {len(args.models)} models. "
        f"At most ${ceiling:.2f}; usually far less."
    )
    if not args.spend:
        out("Nothing sent. Add --spend to run it for real.")
        return 0

    scores = []
    for model in args.models:
        try:
            reader = reader_for(model)
        except TestSetError as error:
            out(f"Cannot run: {error}")
            return 2
        score = Score(model=model)
        for image, expected in cases:
            reading = reader.read(image.read_bytes(), IMAGE_TYPES[image.suffix.lower()])
            score_one(score, image.name, expected, reading)
        scores.append(score)
    report(scores, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
