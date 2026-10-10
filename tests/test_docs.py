"""Every document's references are true (CLAUDE.md section 7.0: the little things too).

Docs rot quietly: a decision renumbered, a file renamed, a link left pointing
nowhere. Each one makes a reader trust the next page less. These tests read
every Markdown file the repository tracks and check what can be checked:

- every decision number (D-NNN) exists in docs/DECISIONS.md;
- every repository path written in backticks exists;
- every relative Markdown link points at a file that exists.

A path that is meant not to exist yet is written without backticks and
without a link, and says "to be written", so it is never mistaken for one
that does.

Two kinds of document are records, written as of their day and never
edited: `docs/DECISIONS.md` (append-only, section 10 of CLAUDE.md) and the
daily reports in `docs/reports/`. Files have moved since some were written,
so their paths are not checked; their decision numbers still are.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "DECISIONS.md"
RECORDS = (DECISIONS, ROOT / "docs" / "reports")

# Numbers reserved for decisions proposed and not yet made. DECISIONS.md
# holds approved decisions only (CLAUDE.md section 10), so these are cited
# as "proposed" without an entry. Each says why; once decided, it moves to
# DECISIONS.md and leaves this list (a test below enforces both).
PROPOSED = {
    "046": (
        "Three platforms (website, Android, iOS), each serving brands and "
        "creators: Adhi's direction of 22 September 2026, awaiting Erode Harish"
    ),
}

DECISION = re.compile(r"\bD-(\d{3})\b")
# `app/...`, `docs/...md`, `tests/...py`: backticked text that is a path.
PATH = re.compile(r"`((?:app|docs|tests|scripts|infra|alembic|\.github)/[\w./-]+)`")
LINK = re.compile(r"\]\((?!https?://|mailto:|#)([^)#\s]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return [ROOT / name for name in sorted(set(listed.split("\0"))) if name]


def is_record(path: Path) -> bool:
    return any(path == record or record in path.parents for record in RECORDS)


def exists(target: str) -> bool:
    """A file, a folder, or a module written without its .py."""
    return (ROOT / target).exists() or (ROOT / f"{target}.py").exists()


def is_branch_name(target: str) -> bool:
    """`docs/design-direction` is a git branch: no extension, no such folder."""
    last = target.rstrip("/").rsplit("/", 1)[-1]
    return target.startswith("docs/") and "." not in last and not target.endswith("/")


def decided() -> set[str]:
    text = DECISIONS.read_text(encoding="utf-8")
    return set(re.findall(r"^## D-(\d{3})\b", text, flags=re.MULTILINE))


def test_the_documents_are_found():
    names = {path.name for path in markdown_files()}
    assert {"CLAUDE.md", "DECISIONS.md", "README.md", "legal.md"} <= names


def test_every_decision_number_exists():
    known = decided() | set(PROPOSED)
    missing = [
        f"{path.relative_to(ROOT)}: D-{number}"
        for path in markdown_files()
        for number in DECISION.findall(path.read_text(encoding="utf-8"))
        if number not in known
    ]

    assert missing == [], "Decisions cited but not in DECISIONS.md:\n" + "\n".join(
        missing
    )


def test_every_backticked_path_exists():
    missing = []
    for path in markdown_files():
        if is_record(path):
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            for target in PATH.findall(line):
                clean = target.rstrip(".,:;")
                if "*" in clean or "<" in clean or is_branch_name(clean):
                    continue  # a pattern or a branch, not one file
                if not exists(clean):
                    missing.append(f"{path.relative_to(ROOT)}:{line_number}: {clean}")

    assert missing == [], "Paths that do not exist:\n" + "\n".join(missing)


def test_every_relative_link_resolves():
    missing = []
    for path in markdown_files():
        if is_record(path):
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            for target in LINK.findall(line):
                if not (path.parent / target).resolve().exists():
                    missing.append(f"{path.relative_to(ROOT)}:{line_number}: {target}")

    assert missing == [], "Links that point nowhere:\n" + "\n".join(missing)


def test_a_proposed_number_is_not_also_decided():
    # Once decided, the number belongs in DECISIONS.md and leaves PROPOSED.
    assert set(PROPOSED) & decided() == set()
