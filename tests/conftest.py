from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine
from tests import migration_check


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
