"""The only way an admin is made, suspended, restored or given a setup ticket (D-061, D-105)."""

from contextlib import nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.auth import second_factor
from app.modules.auth.models.account import Account
from app.modules.auth.models.totp_factor import TotpFactor
from scripts import make_admin
from tests.factories import FIXED_NOW, build_auth_session, create_account, fake_phone


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(settings, "environment", "local")


def run(db, *argv: str) -> int:
    return make_admin.main(
        list(argv), session_factory=lambda: nullcontext(db), now=FIXED_NOW
    )


def account_for(db, phone: str) -> Account | None:
    return db.scalars(select(Account).where(Account.phone == phone)).first()


def test_it_creates_an_admin(local, db, capsys):
    phone = fake_phone()

    assert run(db, phone) == 0

    assert account_for(db, phone).role == "admin"
    assert "Created admin" in capsys.readouterr().out


def test_running_it_twice_changes_nothing(local, db, capsys):
    phone = fake_phone()
    run(db, phone)

    assert run(db, phone) == 0
    assert "Already an admin" in capsys.readouterr().out


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_a_user_is_never_turned_into_an_admin(local, db, capsys, role):
    user = create_account(db, role)

    assert run(db, user.phone) == 1

    assert db.get(Account, user.id).role == role
    assert "separate identity" in capsys.readouterr().err


def test_outside_local_it_needs_yes(monkeypatch, db, capsys):
    monkeypatch.setattr(settings, "environment", "production")
    phone = fake_phone()

    assert run(db, phone) == 1
    assert account_for(db, phone) is None
    assert run(db, phone, "--yes") == 0
    assert account_for(db, phone).role == "admin"


def test_suspending_an_admin_ends_their_sessions(local, db):
    admin = create_account(db, "admin")
    session = build_auth_session(db, account_id=admin.id)
    db.add(session)
    db.flush()

    assert run(db, admin.phone, "--suspend", "abuse") == 0

    db.refresh(admin)
    db.refresh(session)
    assert admin.suspended_at == FIXED_NOW
    assert admin.suspension_reason == "abuse"
    assert session.revoked_at == FIXED_NOW


def test_restoring_an_admin_clears_the_suspension(local, db):
    admin = create_account(db, "admin")
    run(db, admin.phone, "--suspend", "other")

    assert run(db, admin.phone, "--restore") == 0

    db.refresh(admin)
    assert admin.suspended_at is None
    assert admin.suspension_reason is None


def test_it_only_suspends_admins(local, db, capsys):
    creator = create_account(db, "creator")

    assert run(db, creator.phone, "--suspend", "spam") == 1
    assert db.get(Account, creator.id).suspended_at is None


def test_something_that_is_not_a_number_is_refused(local, db):
    assert run(db, "not-a-phone") == 1


# --- setup tickets for the second factor (D-105) -------------------------------------------


def test_it_issues_a_setup_ticket_shown_once(local, db, capsys):
    admin = create_account(db, "admin")
    session = build_auth_session(db, account_id=admin.id)
    db.add(session)
    db.flush()

    assert run(db, admin.phone, "--second-factor") == 0

    out = capsys.readouterr().out
    (ticket,) = [line.strip() for line in out.splitlines() if line.startswith("    ")]
    factor = db.scalars(select(TotpFactor).where(TotpFactor.account_id == admin.id)).one()
    assert factor.ticket_hash == second_factor.hash_ticket(ticket)
    assert ticket not in factor.ticket_hash
    assert factor.ticket_expires_at == FIXED_NOW + timedelta(minutes=15)
    db.refresh(session)
    assert session.revoked_at == FIXED_NOW


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_it_issues_tickets_only_to_admins(local, db, capsys, role):
    user = create_account(db, role)

    assert run(db, user.phone, "--second-factor") == 1

    assert "No admin account" in capsys.readouterr().err
    assert (
        db.scalars(select(TotpFactor).where(TotpFactor.account_id == user.id)).first()
        is None
    )


def test_a_suspended_admin_gets_no_ticket(local, db, capsys):
    admin = create_account(db, "admin")
    run(db, admin.phone, "--suspend", "abuse")

    assert run(db, admin.phone, "--second-factor") == 1

    assert "suspended" in capsys.readouterr().err


def test_a_new_admin_is_told_to_get_a_ticket(local, db, capsys):
    assert run(db, fake_phone()) == 0

    assert "--second-factor" in capsys.readouterr().out
