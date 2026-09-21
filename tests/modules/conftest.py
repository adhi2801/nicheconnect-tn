"""Fixtures shared by the module tests.

A test module that needs something different defines its own `clock` or
`client`, and pytest uses that one instead of these.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from tests.deal_flow import Clock
from tests.factories import FIXED_NOW


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def client(db: Session, clock: Clock) -> Iterator[TestClient]:
    """The app, on the rolled-back test session, seeing the test's clock."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()
