"""Every Markdown file has a row in docs/DOCS_STATUS.md, and the rows tell the truth.

Adhi, 15 November 2026: all 102 .md files at the bar, "proper", not in words.
The bar is `docs/README.md` section 0. These tests hold the record of which
files meet it, so it cannot drift or be claimed:

- every tracked .md file has exactly one row, and no row names a missing file;
- each file's kind follows from where it lives: records (the decision log,
  reports, decided papers, assignments) keep what was true when written and
  need only a status line; generated files are a tool's output, exempt with
  the reason given; everything else is a living document held to the bar;
- a row marked passed gives the date it was checked and its evidence, and a
  living document marked passed says "Checked against the code on <that
  date>" in its first lines, so the claim is visible in the file itself;
- the count line at the top is what the rows say.

What the machine cannot judge (true today, sourced, benchmarked) is judged by
the independent review (D-139, D-193) reading the file against the code; its
findings are the evidence a passed row cites.
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "DOCS_STATUS.md"

RECORD = re.compile(
    r"^(docs/reports/|docs/decided/|docs/DECISIONS\.md$|docs/assignments/)"
)
GENERATED = {
    "frontend/apps/mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/README.md": (
        "Flutter's template note inside an iOS asset folder"
    ),
    "frontend/apps/web/AGENTS.md": "Next.js's agent rules, rewritten by its own tooling",
    "frontend/apps/web/CLAUDE.md": "one line importing AGENTS.md",
}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
CHECKED = re.compile(
    rf"[Cc]hecked against the code(?: on)?,? (\d{{1,2}} (?:{MONTHS}) 20\d\d)"
)
ROW = re.compile(
    r"^\| `(?P<file>[^`]+)` \|(?P<kind>[^|]*)\|(?P<status>[^|]*)\|(?P<checked>[^|]*)\|(?P<evidence>.*)\|$"
)
COUNT = re.compile(r"\*\*Passed: (\d+) of (\d+)\*\*")
STATUSES = {"passed", "not yet", "exempt"}


def tracked() -> set[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return {name for name in listed.split("\0") if name}


def rows() -> list[dict[str, str]]:
    """Every table row of DOCS_STATUS.md, its cells stripped."""
    found = []
    for line in STATUS.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            found.append({key: value.strip() for key, value in match.groupdict().items()})
    return found


def kind_of(name: str) -> str:
    if name in GENERATED:
        return "generated"
    return "record" if RECORD.match(name) else "living"


def first_lines(name: str) -> str:
    return "\n".join((ROOT / name).read_text(encoding="utf-8").splitlines()[:8])


def test_every_markdown_file_has_exactly_one_row() -> None:
    named = [row["file"] for row in rows()]
    duplicates = sorted({name for name in named if named.count(name) > 1})
    assert duplicates == [], duplicates
    missing = sorted(tracked() - set(named))
    assert missing == [], "Add a row to docs/DOCS_STATUS.md for:\n" + "\n".join(missing)


def test_no_row_names_a_file_that_does_not_exist() -> None:
    gone = sorted({row["file"] for row in rows()} - tracked())
    assert gone == [], gone


def test_each_rows_kind_follows_from_where_the_file_lives() -> None:
    wrong = [
        (row["file"], row["kind"])
        for row in rows()
        if row["kind"] != kind_of(row["file"])
    ]
    assert wrong == [], wrong


def test_each_row_has_a_known_status() -> None:
    unknown = [
        (row["file"], row["status"]) for row in rows() if row["status"] not in STATUSES
    ]
    assert unknown == [], unknown


def test_only_a_generated_file_is_exempt_and_it_says_why() -> None:
    for row in rows():
        assert (row["status"] == "exempt") == (row["kind"] == "generated"), row
        if row["kind"] == "generated":
            assert row["evidence"], row


def test_a_passed_row_gives_its_date_and_its_evidence() -> None:
    for row in (r for r in rows() if r["status"] == "passed"):
        checked = datetime.strptime(row["checked"], "%d %B %Y").date()  # noqa: DTZ007
        assert checked <= datetime.now(ZoneInfo("Asia/Kolkata")).date(), row
        assert len(row["evidence"]) >= 20, (
            f"{row['file']}: say what was checked and where"
        )


@pytest.mark.parametrize(
    "row",
    [r for r in rows() if r["status"] == "passed" and r["kind"] == "living"],
    ids=lambda r: r["file"],
)
def test_a_passed_living_document_says_so_in_its_first_lines(row: dict[str, str]) -> None:
    match = CHECKED.search(first_lines(row["file"]))
    assert match, (
        f"{row['file']}: its first lines must say 'Checked against the code on {row['checked']}'"
    )
    assert match.group(1) == row["checked"], (row["file"], match.group(1), row["checked"])


def test_the_count_line_is_what_the_rows_say() -> None:
    match = COUNT.search(STATUS.read_text(encoding="utf-8"))
    assert match, "the count line '**Passed: N of M**' is missing"
    table = rows()
    passed = sum(1 for row in table if row["status"] == "passed")
    must = sum(1 for row in table if row["status"] != "exempt")
    assert (int(match.group(1)), int(match.group(2))) == (passed, must)
