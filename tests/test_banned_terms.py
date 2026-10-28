"""The money words never appear anywhere in the repository (CLAUDE.md section 2).

`docs/standards/testing.md` listed this as CI gate 7 from the start; until 8
October 2026 nothing enforced it beyond one export test. This scans every
file git tracks, code, docs, migrations and reports alike, and every commit
message, which the rule names too.

It also scans files git does not track yet but would commit (anything not
ignored). On 8 October a new file breached the rule, passed here because it
was untracked, and failed CI once committed: the laptop must see what CI will.

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


def git(*args: str) -> str:
    return subprocess.run(  # noqa: S603 - only this file's own git arguments
        ["git", *args],  # noqa: S607 - git is on PATH in CI and locally
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", errors="replace")


def committable_text_files() -> list[Path]:
    """Tracked files, and untracked ones that are not ignored."""
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return [ROOT / name for name in sorted(set(listed.split("\0"))) if name]


def states_the_rule(line: str) -> bool:
    lowered = line.lower()
    return all(word in lowered for word in BANNED)


def test_no_file_uses_a_banned_money_word():
    breaches: list[str] = []
    for path in committable_text_files():
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


def test_no_commit_message_uses_a_banned_money_word():
    # CI checks out the whole history (fetch-depth: 0); a shallow copy would
    # check one commit and pass on the rest unseen.
    assert git("rev-parse", "--is-shallow-repository").strip() == "false"
    messages = git("log", "--format=%H%n%B%x00", "HEAD").split("\0")

    breaches = [
        f"{message.strip()[:12]}: {line.strip()[:120]}"
        for message in messages
        for line in message.splitlines()[1:]
        if PATTERN.search(line) and not states_the_rule(line)
    ]

    assert breaches == [], "Banned money words in commit messages:\n" + "\n".join(
        breaches
    )


def test_the_check_catches_a_breach():
    # Built from parts, or this file would breach its own rule.
    breach = "Funds are held in " + "Esc" + "row until delivery"
    assert PATTERN.search(breach)
    assert not states_the_rule(breach)
    assert states_the_rule(
        'Never: "escrow", "wallet", "guaranteed funds", "split settlement"'
    )
