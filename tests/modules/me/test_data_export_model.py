"""The database's own rules for a data export (D-111), broken with raw SQL."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.me.export_models import EXPORT_KEPT_FOR, MAX_BUILD_ATTEMPTS, DataExport
from tests.factories import FIXED_NOW, create_account

READY = FIXED_NOW + timedelta(minutes=2)


def _insert(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "requested_at": FIXED_NOW,
        "ready_at": READY,
        "expires_at": READY + EXPORT_KEPT_FOR,
        "size_bytes": 1234,
        "downloaded_at": None,
        "failed_at": None,
        "file_deleted_at": None,
        "attempts": 0,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO data_export (account_id, requested_at, ready_at, expires_at, "
            "size_bytes, downloaded_at, failed_at, file_deleted_at, attempts) VALUES "
            "(:account_id, :requested_at, :ready_at, :expires_at, :size_bytes, "
            ":downloaded_at, :failed_at, :file_deleted_at, :attempts)"
        ),
        values,
    )


def preparing(**overrides: object) -> dict[str, object]:
    return {"ready_at": None, "expires_at": None, "size_bytes": None, **overrides}


def test_a_ready_export_and_one_being_prepared_are_kept(db):
    account = create_account(db, "creator")

    _insert(db, account.id, downloaded_at=READY + timedelta(hours=1))
    _insert(db, account.id, **preparing())

    assert (
        len(
            db.scalars(
                select(DataExport).where(DataExport.account_id == account.id)
            ).all()
        )
        == 2
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"expires_at": None}, "ready_has_a_file"),
        ({"size_bytes": None}, "ready_has_a_file"),
        (preparing(size_bytes=10), "ready_has_a_file"),
        ({"expires_at": READY + timedelta(hours=25)}, "expires_a_day_after_ready"),
        ({"size_bytes": 0}, "size_positive"),
        (
            {
                "ready_at": FIXED_NOW - timedelta(seconds=1),
                "expires_at": FIXED_NOW - timedelta(seconds=1) + EXPORT_KEPT_FOR,
            },
            "ready_after_asked",
        ),
        ({"downloaded_at": READY - timedelta(seconds=1)}, "downloaded_while_ready"),
        ({"downloaded_at": READY + EXPORT_KEPT_FOR}, "downloaded_while_ready"),
        (preparing(downloaded_at=READY), "downloaded_while_ready"),
        ({"failed_at": READY, "attempts": MAX_BUILD_ATTEMPTS}, "failed_never_ready"),
        (
            preparing(
                failed_at=FIXED_NOW - timedelta(seconds=1), attempts=MAX_BUILD_ATTEMPTS
            ),
            "failed_never_ready",
        ),
        (preparing(attempts=-1), "attempts_range"),
        (preparing(attempts=MAX_BUILD_ATTEMPTS + 1), "attempts_range"),
        (preparing(failed_at=FIXED_NOW, attempts=1), "failed_after_every_try"),
        (preparing(file_deleted_at=READY), "deleted_only_once_made"),
    ],
)
def test_the_database_refuses_a_bad_row(db, overrides, constraint):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match=f"ck_data_export_{constraint}"):
        _insert(db, account.id, **overrides)


def test_one_export_is_prepared_at_a_time(db):
    account = create_account(db, "creator")
    _insert(db, account.id, **preparing())

    with pytest.raises(IntegrityError, match="uq_data_export_one_preparing"):
        _insert(
            db, account.id, **preparing(requested_at=FIXED_NOW + timedelta(minutes=1))
        )


def test_a_failed_one_does_not_hold_the_place_of_the_next(db):
    account = create_account(db, "creator")
    _insert(db, account.id, **preparing(failed_at=FIXED_NOW, attempts=MAX_BUILD_ATTEMPTS))

    _insert(db, account.id, **preparing(requested_at=FIXED_NOW + timedelta(minutes=1)))


def test_exports_go_with_their_account(db):
    account = create_account(db, "creator")
    _insert(db, account.id)

    db.delete(account)
    db.flush()

    assert (
        db.scalars(select(DataExport).where(DataExport.account_id == account.id)).first()
        is None
    )
