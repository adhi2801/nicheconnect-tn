"""The money words never appear anywhere in the repository (CLAUDE.md section 2).

`docs/standards/testing.md` listed this as CI gate 7 from the start; until 8
October 2026 nothing enforced it beyond one export test. This scans every
file git tracks, code, docs, migrations and reports alike.

A line may name a banned word only to state the rule itself, and the rule is
always stated with all four together, so that is the one exception: a line
naming all four is the rule; a line naming fewer is a breach.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("escrow", "wallet", "guaranteed funds", "split settlement")
PATTERN = re.compile("|".join(re.escape(word) for word in BANNED), re.IGNORECASE)


def tracked_text_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 - git is on PATH in CI and locally
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return [ROOT / name for name in listed.split("\0") if name]


def states_the_rule(line: str) -> bool:
    lowered = line.lower()
    return all(word in lowered for word in BANNED)


def test_no_tracked_file_uses_a_banned_money_word():
    breaches: list[str] = []
    for path in tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError, IsADirectoryError:
            continue  # images, archives, and files deleted but not yet committed
        for number, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line) and not states_the_rule(line):
                breaches.append(
                    f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}"
                )
    assert breaches == [], "Banned money words (CLAUDE.md section 2):\n" + "\n".join(
        breaches
    )


def test_the_check_catches_a_breach():
    assert PATTERN.search("Funds are held in Escrow until delivery")
    assert not states_the_rule("Funds are held in escrow until delivery")
    assert states_the_rule(
        'Never: "escrow", "wallet", "guaranteed funds", "split settlement"'
    )
