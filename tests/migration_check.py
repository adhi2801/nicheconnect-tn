"""Is the test database migrated? Asked once, before any test runs.

Review finding, PR #4: on a database nobody has migrated, the first test to
touch a table fails with UndefinedTable, and so do dozens after it, none
saying the actual problem. This turns that into one line naming the fix.

Reaching the database is not required: when it is down, the tests that need
it fail with a plain connection error, and the tests that do not still run.
"""

from collections.abc import Collection
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[1]
FIX = "uv run alembic upgrade head"


def expected_heads() -> set[str]:
    config = Config(str(ROOT / "alembic.ini"))
    # Absolute, so the check works whatever directory pytest starts in.
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


def problem(current: Collection[str], expected: Collection[str]) -> str | None:
    """What is wrong, in one line, or None when the database is current."""
    if set(current) == set(expected):
        return None
    at = ", ".join(sorted(current)) or "no migration at all"
    want = ", ".join(sorted(expected))
    return f"The test database is at {at}, not {want}. Run: {FIX}"


def check(engine: Engine) -> str | None:
    """The problem with this database, or None if it is current or unreachable."""
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_heads()
    except OperationalError:
        return None
    return problem(current, expected_heads())
