"""Run Squawk over the migrations this branch adds, and nothing else (D-047).

Squawk reads the SQL a migration would run and flags what would lock a busy
table: a new NOT NULL column, a column type change, an index dropped without
CONCURRENTLY, a migration with no lock or statement timeout. Catching that in
review is the whole point, because in production it is an outage.

It runs on the migrations this branch ADDS, not on the whole chain. The 20
migrations already on main raise 47 findings between them, mostly
`prefer-text-field` about `VARCHAR(n)` columns. Those are real, but they are
a schema-wide design question for the Data track, not something a branch
adding one table can answer, and a check that is loud about things nobody
can fix is a check everyone learns to skip.

Usage:
    python -m scripts.lint_new_migrations [base-ref]

`base-ref` defaults to origin/main. Exits 0 when there is nothing to check.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

VERSIONS = Path("alembic/versions")
DEFAULT_BASE = "origin/main"


def squawk_command() -> str:
    """Where squawk is, whichever way it was installed.

    pip puts it beside the interpreter, which on Windows is venv/Scripts and
    is not on PATH unless the virtual environment is activated. CI installs
    it onto PATH. Look next to this interpreter first, then fall back.
    """
    beside = Path(sys.executable).parent
    for name in ("squawk", "squawk.exe"):
        candidate = beside / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which("squawk")
    if found:
        return found
    print(
        "squawk not found. Install it with: pip install squawk-cli==2.65.0",
        file=sys.stderr,
    )
    raise SystemExit(2)


def added_migrations(base: str) -> list[Path]:
    """Migration files this branch adds that `base` does not have."""
    git = shutil.which("git") or "git"
    result = subprocess.run(  # noqa: S603 - fixed argv, resolved path
        [
            git,
            "diff",
            "--name-only",
            "--diff-filter=A",
            f"{base}...HEAD",
            "--",
            str(VERSIONS),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Could not diff against {base}: {result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return [Path(line) for line in result.stdout.split() if line.endswith(".py")]


def revisions_of(path: Path) -> tuple[str, str]:
    """The `revision` and `down_revision` a migration declares.

    Read from the source rather than imported: importing every migration to
    read two strings would run whatever else is at module level.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, str | None] = {}
    for node in tree.body:
        # Alembic writes these annotated (`revision: str = "abc"`), which is
        # an AnnAssign, but a hand-written migration may use a plain Assign.
        targets: list[ast.expr]
        if isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {
                "revision",
                "down_revision",
            }:
                literal = value.value if isinstance(value, ast.Constant) else None
                found[target.id] = literal if isinstance(literal, str) else None
    revision = found.get("revision")
    if not revision:
        print(f"{path}: no revision found", file=sys.stderr)
        raise SystemExit(2)
    # The first migration has no parent; Alembic spells that "base".
    return revision, found.get("down_revision") or "base"


def sql_for(down: str, revision: str) -> str:
    """The SQL this one migration would run, without touching a database."""
    result = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-m", "alembic", "upgrade", f"{down}:{revision}", "--sql"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(2)
    return result.stdout


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    migrations = added_migrations(base)
    if not migrations:
        print(f"No migrations added against {base}; nothing for Squawk to check.")
        return 0

    squawk = squawk_command()
    failed = False
    for path in migrations:
        revision, down = revisions_of(path)
        print(f"\n=== {path.name}  ({down} -> {revision}) ===", flush=True)
        sql_file = path.with_suffix(".squawk.sql")
        sql_file.write_text(sql_for(down, revision), encoding="utf-8")
        try:
            result = subprocess.run(  # noqa: S603 - fixed argv, resolved path
                [squawk, str(sql_file)], capture_output=True, text=True, check=False
            )
        finally:
            sql_file.unlink(missing_ok=True)
        print(result.stdout or result.stderr, flush=True)
        # Squawk exits 0 even when it reports findings, so read its summary.
        if result.returncode != 0 or "Found 0 issues" not in (
            result.stdout + result.stderr
        ):
            failed = True

    if failed:
        print(
            "\nSquawk flagged a new migration. Each rule explains itself at "
            "https://squawkhq.com/docs/rules — fix it, or say in the pull "
            "request why the lock is acceptable here.",
            file=sys.stderr,
        )
        return 1
    print("\nSquawk is happy with every migration this branch adds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
