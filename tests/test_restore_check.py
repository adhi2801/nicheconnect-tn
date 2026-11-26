"""The monthly restore test's checks on a copy (item 90, D-205), against real PostgreSQL.

Two scratch databases stand in for production and its restored copy:
"production" is migrated to head by the real release step
(`python -m app.db.prepare`, in a process of its own, as the migration task
runs it) and seeded; each test's "copy" is made from it with `CREATE
DATABASE ... TEMPLATE`, which copies it byte for byte, as a restore does.
Both are read as a throwaway app login made by the real `ensure_app_login`,
and both are dropped afterwards, so the shared database is never touched.

A faithful copy passes; each check is then broken on purpose in the copy and
seen to fail by name. The pure rules beside them are tested at their edges.
"""

import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.deadline import Deadline
from app.db import restore_check
from app.db.restore_check import (
    SETTLE,
    count_problem,
    database_problems,
    expected_rights,
    image_heads,
    setting_problems,
    target_problems,
    version_at_least,
)
from app.db.restore_copy import Copy
from app.db.roles import ensure_app_login
from app.modules.admin.models.admin_action import AdminAction
from tests.factories import create_account
from tests.modules.test_app_role import KEPT, SEALED
from tests.owner import owner_engine

ROOT = Path(__file__).resolve().parents[1]
CREATORS = 20
RESTORED_AT = datetime.now(UTC) + timedelta(hours=1)


def owner_url(database: str) -> str:
    return (
        make_url(owner_engine.url)
        .set(database=database)
        .render_as_string(hide_password=False)
    )


def as_owner(database: str) -> Engine:
    return create_engine(owner_url(database), poolclass=NullPool)


def server_statement(statement: str) -> None:
    """CREATE and DROP DATABASE refuse to run inside a transaction."""
    with owner_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.execute(text(statement))


@pytest.fixture(scope="module")
def production() -> Iterator[str]:
    name = f"restore_check_prod_{secrets.token_hex(4)}"
    server_statement(f'CREATE DATABASE "{name}"')
    try:
        env = {**os.environ, "DATABASE_URL": owner_url(name)}
        env.pop("APP_DATABASE_PASSWORD", None)
        # The release step itself, in its own process, so Alembic's logging
        # setup never reaches this one's.
        subprocess.run(
            [sys.executable, "-m", "app.db.prepare"], cwd=ROOT, env=env, check=True
        )
        seeding = as_owner(name)
        with Session(seeding) as db:
            for _ in range(CREATORS):
                create_account(db, "creator")
            admin = create_account(db, "admin")
            for note in ("first", "second", "third"):
                db.add(
                    AdminAction(
                        admin_account_id=admin.id, action="view_account", note=note
                    )
                )
            db.commit()
        seeding.dispose()
        yield name
    finally:
        server_statement(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="module")
def login() -> Iterator[tuple[str, str]]:
    name = f"restore_check_login_{secrets.token_hex(4)}"
    password = secrets.token_hex(20)
    with owner_engine.begin() as connection:
        ensure_app_login(connection, password, login=name)
    try:
        yield name, password
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text(f"DROP ROLE {name}"))


@pytest.fixture
def copy(production) -> Iterator[str]:
    name = f"restore_check_copy_{secrets.token_hex(4)}"
    server_statement(f'CREATE DATABASE "{name}" TEMPLATE "{production}"')
    try:
        yield name
    finally:
        server_statement(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def as_login(login: tuple[str, str], database: str) -> str:
    user, password = login
    return (
        make_url(owner_engine.url)
        .set(username=user, password=password, database=database)
        .render_as_string(hide_password=False)
    )


def problems(production: str, copy: str, login: tuple[str, str]) -> list[str]:
    return database_problems(
        as_login(login, production),
        as_login(login, copy),
        cutoff=RESTORED_AT - SETTLE,
        heads=image_heads(),
        deadline=Deadline(600),
    )


def break_copy(copy: str, *statements: str) -> None:
    engine = as_owner(copy)
    try:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
    finally:
        engine.dispose()


def add_accounts(copy: str, count: int, **fields: object) -> None:
    engine = as_owner(copy)
    try:
        with Session(engine) as db:
            for _ in range(count):
                create_account(db, "creator", **fields)
            db.commit()
    finally:
        engine.dispose()


# --- against real copies ------------------------------------------------------------------


def test_a_faithful_copy_passes_every_check(production, copy, login):
    assert problems(production, copy, login) == []


def test_a_copy_at_an_older_migration_fails(production, copy, login):
    (head,) = image_heads()
    script = restore_check.ScriptDirectory.from_config(restore_check.alembic_config())
    older = script.get_revision(head).down_revision
    break_copy(copy, f"UPDATE alembic_version SET version_num = '{older}'")  # noqa: S608 - a revision id from the scripts

    assert problems(production, copy, login) == [
        f"migration: copy at {older}, image at {head}"
    ]


def test_a_copy_without_pgvector_fails(production, copy, login):
    break_copy(copy, "DROP EXTENSION vector CASCADE")

    assert "pgvector: not installed" in problems(production, copy, login)


def test_a_copy_without_dbos_schema_fails(production, copy, login):
    break_copy(copy, "DROP SCHEMA dbos CASCADE")

    assert problems(production, copy, login) == ["dbos: schema missing"]


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE admin_action SET note = 'rewritten'"
        " WHERE id = (SELECT id FROM admin_action ORDER BY id LIMIT 1)",
        "DELETE FROM admin_action WHERE id = (SELECT id FROM admin_action ORDER BY id LIMIT 1)",
    ],
    ids=["altered", "removed"],
)
def test_a_sealed_row_altered_or_removed_fails(production, copy, login, change):
    break_copy(
        copy,
        "ALTER TABLE admin_action DISABLE TRIGGER USER",
        change,
        "ALTER TABLE admin_action ENABLE TRIGGER USER",
    )

    assert problems(production, copy, login) == [
        "sealed: admin_action differs from production"
    ]


def test_rows_lost_in_the_copy_fail(production, copy, login):
    break_copy(
        copy,
        "DELETE FROM account WHERE id = (SELECT id FROM account WHERE role = 'creator' ORDER BY id LIMIT 1)",
    )

    assert problems(production, copy, login) == [
        f"rows: account has {CREATORS} in the copy, {CREATORS + 1} in production"
    ]


def test_over_one_percent_more_rows_than_production_fails(production, copy, login):
    add_accounts(copy, 2)

    assert problems(production, copy, login) == [
        f"rows: account has {CREATORS + 3} in the copy, over 1% more than {CREATORS + 1}"
    ]


def test_rows_made_after_the_cut_off_are_not_compared(production, copy, login):
    add_accounts(copy, 2, created_at=RESTORED_AT)

    assert problems(production, copy, login) == []


def test_a_table_missing_from_the_copy_fails(production, copy, login):
    break_copy(copy, "DROP TABLE creator_embedding")

    assert problems(production, copy, login) == [
        "rows: creator_embedding missing from the copy"
    ]


@pytest.mark.parametrize(
    "change",
    [
        "REVOKE INSERT ON campaign FROM app_writer",
        "GRANT TRUNCATE ON campaign TO app_writer",
    ],
    ids=["narrowed", "widened"],
)
def test_the_login_s_rights_changed_fail(production, copy, login, change):
    break_copy(copy, change)

    assert problems(production, copy, login) == [
        "rights: campaign grants the wrong rights"
    ]


def test_a_login_with_powers_of_its_own_fails(production, copy, login):
    with owner_engine.begin() as connection:
        connection.execute(text(f"ALTER ROLE {login[0]} CREATEDB"))
    try:
        found = problems(production, copy, login)
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text(f"ALTER ROLE {login[0]} NOCREATEDB"))

    assert found == ["rights: the login has powers of its own or is not app_writer"]


# --- the pure rules -------------------------------------------------------------------------


def test_the_sealed_and_kept_tables_are_item_97_s():
    assert restore_check.SEALED == SEALED
    assert restore_check.KEPT == KEPT


def test_each_table_kind_has_its_own_rights():
    assert expected_rights("alembic_version") == (True,) + (False,) * 6
    assert expected_rights("deal_note") == (True, True) + (False,) * 5
    assert expected_rights("takedown") == (True, True, True) + (False,) * 4
    assert expected_rights("campaign") == (True,) * 4 + (False,) * 3


@pytest.mark.parametrize(
    ("found", "ok"),
    [
        ("0.8.2", True),
        ("0.8.6", True),
        ("0.10.0", True),
        ("1.0", True),
        ("0.8.1", False),
        ("0.8", False),
        ("0.7.9", False),
        ("0.8.x", False),
    ],
)
def test_pgvector_must_be_0_8_2_or_later(found, ok):
    assert version_at_least(found, (0, 8, 2)) is ok


@pytest.mark.parametrize(
    ("production", "copy", "problem"),
    [
        (0, 0, None),
        (100, 100, None),
        (100, 101, None),
        (100, 102, "rows: t has 102 in the copy, over 1% more than 100"),
        (100, 99, "rows: t has 99 in the copy, 100 in production"),
        (0, 1, "rows: t has 1 in the copy, over 1% more than 0"),
    ],
)
def test_the_copy_holds_production_s_rows_and_at_most_one_percent_more(
    production, copy, problem
):
    assert count_problem("t", production, copy) == problem


def made(**overrides: object) -> Copy:
    fields: dict[str, object] = {
        "identifier": "nicheconnect-production-restore-check-20261201-0230",
        "host": "copy.internal",
        "port": 5432,
        "public": False,
        "encrypted": True,
        "deletion_protection": False,
        "backups_kept_days": 0,
    }
    fields.update(overrides)
    return Copy(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"public": True}, "copy: publicly accessible"),
        ({"encrypted": False}, "copy: not encrypted"),
        ({"deletion_protection": True}, "copy: deletion protection on"),
        ({"backups_kept_days": 1}, "copy: keeps backups"),
    ],
)
def test_a_copy_that_is_public_unencrypted_protected_or_backed_up_fails(
    override, problem
):
    assert setting_problems(made()) == []
    assert setting_problems(made(**override)) == [problem]


@pytest.mark.parametrize(
    ("rto", "rpo", "found"),
    [
        (timedelta(hours=1), timedelta(minutes=5), []),
        (None, timedelta(minutes=5), []),
        (
            timedelta(hours=1, seconds=1),
            timedelta(0),
            ["target: restore took 3601 s, over 3600"],
        ),
        (
            timedelta(0),
            timedelta(minutes=5, seconds=1),
            ["target: 301 s would be lost, over 300"],
        ),
    ],
)
def test_a_restore_over_an_hour_or_over_five_minutes_lost_fails(rto, rpo, found):
    assert target_problems(rto, rpo) == found
