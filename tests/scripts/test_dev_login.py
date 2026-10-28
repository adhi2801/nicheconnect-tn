"""The local login command (D-059): a token for a local account, and nothing else."""

from contextlib import nullcontext
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from scripts import dev_login
from tests.factories import FIXED_NOW, create_account

# In the seed script's range, but beyond the numbers it hands out.
SAMPLE = "+919000099001"


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(settings, "environment", "local")


def run(db, *argv: str) -> int:
    return dev_login.main(
        list(argv), session_factory=lambda: nullcontext(db), now=FIXED_NOW
    )


def test_it_prints_a_token_the_api_accepts(local, db, capsys):
    account = create_account(db, "creator", phone=SAMPLE)

    assert run(db, SAMPLE) == 0
    token = capsys.readouterr().out.strip()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: FIXED_NOW + timedelta(minutes=1)
    try:
        response = TestClient(app).get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(account.id)
    assert response.json()["role"] == "creator"


def test_only_the_token_goes_to_stdout(local, db, capsys):
    r"""So `$token = python scripts\dev_login.py ...` captures exactly the token."""
    create_account(db, "brand", phone=SAMPLE)

    run(db, SAMPLE)
    out, err = capsys.readouterr()

    assert len(out.strip().splitlines()) == 1
    assert "Role: brand" in err


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_it_refuses_outside_local(monkeypatch, db, capsys, environment):
    monkeypatch.setattr(settings, "environment", environment)
    create_account(db, "creator", phone=SAMPLE)

    assert run(db, SAMPLE) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "not 'local'" in err


def test_a_real_looking_number_needs_any_phone(local, db, capsys):
    create_account(db, "creator", phone="+919876543210")

    assert run(db, "+919876543210") == 1
    assert "--any-phone" in capsys.readouterr().err
    assert run(db, "+919876543210", "--any-phone") == 0


def test_numbers_are_matched_however_they_are_typed(local, db, capsys):
    create_account(db, "creator", phone=SAMPLE)

    assert run(db, "90000 99001") == 0


def test_an_unknown_number_says_how_to_fix_it(local, db, capsys):
    assert run(db, "+919000099998") == 1
    assert "seed_dev_data.py" in capsys.readouterr().err


def test_something_that_is_not_a_number_is_refused(local, db, capsys):
    assert run(db, "not-a-phone") == 1
    assert capsys.readouterr().out == ""
