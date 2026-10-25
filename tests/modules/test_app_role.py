"""The app's own database login can do what the app does, and nothing more (item 97, D-100).

The login is made here by the real `ensure_app_login`, exactly as the
release step makes it, with a name of its own so runs never collide, and
removed afterwards. Roles belong to the whole server, so it is committed for
real; everything done while logged in as it is rolled back.

Three kinds of proof:
- what the login may not do: change or empty a sealed table, switch off a
  trigger, change the replication role, create or drop a table, write the
  migration version;
- what every table grants it, read from the catalogue, so a table added
  later without the right rights fails here;
- a whole deal, a dispute, a report and its outcome, and the data export,
  run through the API on a session logged in as it.
"""

import secrets
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db.roles import APP_WRITER, UnsafeAppPassword, ensure_app_login, scram_verifier
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.factories import create_account
from tests.owner import owner_engine
from tests.step_up import download_export

SEALED = {
    "admin_action",
    "deal_note",
    "deal_record_checkpoint",
    "deal_record_entry",
    "deal_record_timestamp",
    "dispute_event",
}
# Added to and changed, never removed: a takedown is the record the IT Rules
# ask us to keep (item 52, rule 3(1)(g)).
KEPT = {"takedown"}


def login_url(name: str, password: str) -> str:
    return (
        make_url(owner_engine.url)
        .set(username=name, password=password)
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="module")
def login() -> Iterator[tuple[str, str]]:
    name = f"app_login_test_{secrets.token_hex(4)}"
    password = secrets.token_hex(20)
    with owner_engine.begin() as connection:
        ensure_app_login(connection, password, login=name)
    try:
        yield name, password
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text(f"DROP ROLE {name}"))


@pytest.fixture(scope="module")
def app_engine(login) -> Iterator[Engine]:
    as_app = create_engine(login_url(*login), pool_pre_ping=True)
    try:
        yield as_app
    finally:
        as_app.dispose()


@pytest.fixture
def app_db(app_engine) -> Iterator[Session]:
    """A session logged in as the app's login, rolled back after the test."""
    connection = app_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def refused(app_db: Session, statement: str) -> str:
    with pytest.raises(ProgrammingError) as caught, app_db.begin_nested():
        app_db.execute(text(statement))
    return str(caught.value.orig)


# --- the login itself -----------------------------------------------------------------


def test_the_login_takes_its_password_and_no_other(login):
    name, password = login
    with create_engine(login_url(name, password)).connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar() == name
    with pytest.raises(OperationalError):
        create_engine(login_url(name, "wrong" + password)).connect()


def test_releasing_again_changes_the_password(login):
    name, password = login
    new = secrets.token_hex(20)
    with owner_engine.begin() as connection:
        ensure_app_login(connection, new, login=name)
    try:
        with create_engine(login_url(name, new)).connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar() == 1
        with pytest.raises(OperationalError):
            create_engine(login_url(name, password)).connect()
    finally:
        with owner_engine.begin() as connection:
            ensure_app_login(connection, password, login=name)


def test_the_login_holds_no_power_of_its_own(login):
    with owner_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,"
                " pg_has_role(rolname, :writer, 'MEMBER') FROM pg_roles WHERE rolname = :name"
            ),
            {"name": login[0], "writer": APP_WRITER},
        ).one()

    assert tuple(row) == (False, False, False, False, False, True)


@pytest.mark.parametrize(
    "password", ["short1", "x" * 31, "has spaces in it " * 3, "é" * 40]
)
def test_an_unsafe_password_is_refused(password):
    with pytest.raises(UnsafeAppPassword):
        scram_verifier(password)


def test_the_verifier_is_postgres_s_shape_and_never_the_password():
    password = "A" * 40
    verifier = scram_verifier(password, salt=b"0123456789abcdef")

    assert verifier.startswith("SCRAM-SHA-256$4096:MDEyMzQ1Njc4OWFiY2RlZg==$")
    assert password not in verifier
    assert scram_verifier(password) != scram_verifier(password)  # a new salt each time


# --- what it may not do --------------------------------------------------------------


@pytest.mark.parametrize("table", sorted(SEALED))
def test_sealed_tables_refuse_it_by_permission(app_db, table):
    """Refused before the triggers are reached: protected twice."""
    for statement in (
        f"UPDATE {table} SET id = id WHERE false",  # noqa: S608 - a table from the fixed list above
        f"DELETE FROM {table} WHERE false",  # noqa: S608 - a table from the fixed list above
        f"TRUNCATE {table}",
    ):
        assert "permission denied" in refused(app_db, statement)


@pytest.mark.parametrize("table", sorted(KEPT))
def test_kept_tables_refuse_removal_by_permission(app_db, table):
    for statement in (
        f"DELETE FROM {table} WHERE false",  # noqa: S608 - a table from the fixed list above
        f"TRUNCATE {table}",
    ):
        assert "permission denied" in refused(app_db, statement)


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE deal_record_entry DISABLE TRIGGER ALL",
        "ALTER TABLE admin_action DISABLE TRIGGER admin_action_no_update_or_delete",
        "DROP TABLE campaign",
        "CREATE TABLE public.sneaky (id int)",
        "CREATE SCHEMA sneaky",
        "SET session_replication_role = replica",
        "TRUNCATE notification",
        "INSERT INTO alembic_version VALUES ('ffffffffffff')",
        "ALTER ROLE app_writer LOGIN",
    ],
)
def test_it_cannot_reach_around_the_rules(app_db, statement):
    message = refused(app_db, statement)

    assert "permission denied" in message or "must be owner" in message


# --- what every table grants it --------------------------------------------------------


def test_every_table_grants_exactly_the_rights_the_app_needs():
    with owner_engine.connect() as connection:
        rights = {
            table: tuple(
                connection.execute(
                    text(f"SELECT has_table_privilege(:role, :table, '{p}')"),
                    {"role": APP_WRITER, "table": f"public.{table}"},
                ).scalar()
                for p in (
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "REFERENCES",
                    "TRIGGER",
                )
            )
            for (table,) in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }

    expected = {
        table: (
            (True, False, False, False, False, False, False)
            if table == "alembic_version"
            else (True, True, False, False, False, False, False)
            if table in SEALED
            else (True, True, True, False, False, False, False)
            if table in KEPT
            else (True, True, True, True, False, False, False)
        )
        for table in rights
    }
    assert len(rights) >= 30
    assert rights == expected


def test_a_table_made_later_gets_row_rights_by_default():
    """ALTER DEFAULT PRIVILEGES, proven on a table made inside a rolled-back transaction."""
    with owner_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text("CREATE TABLE public.made_later (id int)"))
        allowed = connection.execute(
            text("SELECT has_table_privilege(:role, 'public.made_later', 'UPDATE')"),
            {"role": APP_WRITER},
        ).scalar()
        transaction.rollback()

    assert allowed is True


# --- the app, logged in as it ---------------------------------------------------------


@pytest.fixture
def app_client(app_db, clock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_now] = lambda: clock.now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_a_whole_deal_runs_on_the_app_s_own_login(app_client, app_db, clock):
    client = app_client
    brand, creator = brand_user(app_db, clock), creator_user(app_db, clock)
    memo_id = accepted_memo(client, brand, creator)

    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert proof.status_code == 201, proof.text
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof.json()['id']}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text
    paid = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678901"},
        headers=brand.headers,
    )
    assert paid.status_code == 200, paid.text
    disputed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json={
            "reason": "The payment was marked sent but nothing has reached my account."
        },
        headers=creator.headers,
    )
    assert disputed.status_code == 201, disputed.text
    added = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute/entries",
        json={"note": "My bank statement for that week shows nothing."},
        headers=creator.headers,
    )
    assert added.status_code == 201, added.text
    record = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers)
    assert record.status_code == 200 and record.json()["intact"] is True, record.text
    export = download_export(client, creator.headers)
    assert export.status_code == 200, export.text


def test_a_report_and_its_outcome_run_on_the_app_s_own_login(app_client, app_db, clock):
    client = app_client
    reporter = brand_user(app_db, clock)
    reported = creator_user(app_db, clock)
    admin_account = create_account(app_db, "admin")
    app_db.commit()
    admin = User(admin_account.id, "admin", clock)
    creator_id = app_db.execute(
        text("SELECT id FROM creator WHERE account_id = :a"), {"a": reported.account_id}
    ).scalar_one()

    filed = client.post(
        "/api/v1/reports",
        json={
            "subject_kind": "creator",
            "subject_id": str(creator_id),
            "category": "fake_profile",
        },
        headers=reporter.headers,
    )
    assert filed.status_code == 201, filed.text
    resolved = client.post(
        f"/api/v1/admin/reports/{filed.json()['id']}/resolve",
        json={"outcome": "dismissed", "note": "Looked genuine."},
        headers=admin.headers,
    )
    assert resolved.status_code == 200, resolved.text
    mine = client.get("/api/v1/reports/mine", headers=reporter.headers).json()["items"]
    assert mine[0]["status"] == "dismissed"
    # A block writes and then filters every later search (item 59).
    blocked = client.post(
        "/api/v1/me/blocks",
        json={"creator_id": str(creator_id)},
        headers=reporter.headers,
    )
    assert blocked.status_code == 201, blocked.text


def test_a_takedown_and_its_lift_run_on_the_app_s_own_login(app_client, app_db, clock):
    """Withholding writes the takedown, the sealed log and a notification (item 52)."""
    client = app_client
    owner = creator_user(app_db, clock)
    admin_account = create_account(app_db, "admin")
    app_db.commit()
    admin = User(admin_account.id, "admin", clock)
    creator_id = app_db.execute(
        text("SELECT id FROM creator WHERE account_id = :a"), {"a": owner.account_id}
    ).scalar_one()

    withheld = client.post(
        "/api/v1/admin/takedowns",
        json={
            "subject_kind": "creator",
            "subject_id": str(creator_id),
            "basis": "court_order",
            "issued_by": "High Court of Madras",
            "order_reference": "WP 1012 of 2026",
            "received_at": clock.now.isoformat(),
            "note": "The order names this profile.",
        },
        headers=admin.headers,
    )
    assert withheld.status_code == 201, withheld.text
    lifted = client.post(
        f"/api/v1/admin/takedowns/{withheld.json()['id']}/lift",
        json={"note": "The order was set aside."},
        headers=admin.headers,
    )
    assert lifted.status_code == 200, lifted.text
    mine = client.get("/api/v1/me/takedowns", headers=owner.headers)
    assert mine.json()["items"][0]["lifted_at"] is not None
