from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@pytest.fixture
def db() -> Iterator[Session]:
    """A database session whose changes are rolled back after each test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
