import os
from collections.abc import Iterator

import pytest
from hypothesis import settings
from sqlalchemy.orm import Session

from app.db.session import engine
from tests import migration_check

# Property tests (D-090). Every profile has no deadline: a slow machine is
# not a bug, and a test that fails only when the machine is busy is flaky
# (testing.md section 10). Locally 200 cases each; CI sets
# HYPOTHESIS_PROFILE=ci for 1,000, and prints how to replay any failure.
settings.register_profile(
    "dev",
    max_examples=200,
    deadline=None,
)
settings.register_profile(
    "ci",
    max_examples=1000,
    deadline=None,
    print_blob=True,
    database=None,
)
# Mutation testing runs the chosen tests once per mutant, thousands of times:
# fewer cases each, so a night is enough (D-091).
settings.register_profile("mutation", max_examples=50, deadline=None, database=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def db() -> Iterator[Session]:
    """A database session whose changes, even commits, are rolled back after each test.

    The session runs inside an outer transaction; its commits only release
    savepoints, so nothing reaches the real database (testing.md section 3).
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


def pytest_sessionstart(session: pytest.Session) -> None:
    """Stop at once, naming the fix, if the database is not migrated."""
    found = migration_check.check(engine)
    if found:
        pytest.exit(found, returncode=3)
