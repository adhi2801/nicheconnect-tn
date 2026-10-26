"""The rules of database.md that a reading of the migrated schema can check.

Until 14 October 2026 these were written in the standard and held only while
someone read migrations for them; one of them (every foreign key indexed) had
already been broken three times unnoticed. Each test reads the real migrated
database through PostgreSQL's own catalogue, so it sees what the migrations
made, not what the models say.

A rule with known exceptions names them here, with the reason, and fails
both ways: when a new table breaks the rule, and when a named exception is
fixed, so the list never outlives the truth.
"""

import pathlib

import pytest
from sqlalchemy import text

import app.db.models  # noqa: F401 - registers every table, as the app does
from app.db.base import Base
from app.db.session import engine

TABLES = sorted(Base.metadata.tables)

# Tables made before uuidv7() became the rule (database.md section 2, 8 October
# 2026; PostgreSQL 18). Changing a primary key's default is harmless, but
# re-keying rows is not, and none of these needs it.
RANDOM_ID_TABLES = {
    "account",
    "application",
    "auth_session",
    "brand",
    "campaign",
    "creator",
    "creator_channel",
    "creator_package",
    "deal_memo",
    "deliverable_proof",
    "dispute",
    "dispute_event",
    "notification",
    "otp_challenge",
    "payment_status",
}
# Keyed by their owner's id: exactly one current embedding each (D-052).
OWNER_KEYED_TABLES = {"campaign_embedding", "creator_embedding"}
# Append-only, sealed by triggers (D-057): never updated, so no updated_at.
APPEND_ONLY_TABLES = {
    "admin_action",
    "deal_note",
    "deal_record_checkpoint",
    "deal_record_entry",
    "deal_record_timestamp",
}
# Sealed the same way: those above, and dispute events since item 99, which
# keep an updated_at that always equals created_at.
SEALED_TABLES = APPEND_ONLY_TABLES | {"dispute_event"}
# A deal record entry's moment is `recorded_at`, which is inside its seal and
# set by the app, so it has no created_at either (D-057 point 3).
NO_CREATED_AT = {"deal_record_entry"}

# The one money column on a table with no currency of its own: a creator's
# quote answers a campaign, and is in the campaign's currency.
PAISE_WITHOUT_CURRENCY = {("application", "quoted_amount_paise")}

# Constraints a test cannot break on their own, with the reason.
UNBREAKABLE_ALONE = {
    # UNIQUE (id, role) exists so profile tables can point at an account and
    # its role together; id is already the primary key, so no row can break
    # this without breaking that first.
    "uq_account_id_role",
}


def rows(sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


@pytest.fixture(scope="module")
def columns() -> dict[str, dict[str, tuple[str, int | None]]]:
    """table -> column -> (data type, character limit), as migrated."""
    found: dict[str, dict[str, tuple[str, int | None]]] = {}
    for table, column, data_type, limit in rows(
        "SELECT table_name, column_name, data_type, character_maximum_length "
        "FROM information_schema.columns WHERE table_schema = 'public'"
    ):
        found.setdefault(table, {})[column] = (data_type, limit)
    return found


@pytest.fixture(scope="module")
def checks() -> dict[str, list[str]]:
    """table -> the definitions of its CHECK constraints."""
    found: dict[str, list[str]] = {}
    for table, definition in rows(
        "SELECT c.relname, pg_get_constraintdef(k.oid) FROM pg_constraint k "
        "JOIN pg_class c ON c.oid = k.conrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND k.contype = 'c'"
    ):
        found.setdefault(table, []).append(definition)
    return found


def test_the_catalogue_is_read(columns, checks):
    """Guards every test below: on an empty reading they would all pass."""
    assert len(TABLES) >= 30
    assert set(TABLES) <= set(columns)
    assert sum(map(len, checks.values())) > 150


# --- section 2: column types ------------------------------------------------------------


def test_new_tables_take_time_ordered_ids():
    defaults = dict(
        rows(
            "SELECT table_name, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'id'"
        )
    )
    random = {t for t in TABLES if "gen_random_uuid" in (defaults.get(t) or "")}
    neither = {
        t for t in TABLES if "uuidv7" not in (defaults.get(t) or "") and t not in random
    }

    assert random == RANDOM_ID_TABLES
    assert neither == OWNER_KEYED_TABLES


def test_no_time_without_a_zone_and_no_inexact_numbers(columns):
    wrong = [
        (table, column, data_type)
        for table in TABLES
        for column, (data_type, _) in columns[table].items()
        if data_type
        in {"timestamp without time zone", "real", "double precision", "numeric", "money"}
    ]

    assert wrong == []


def test_every_moment_is_a_zoned_timestamp(columns):
    wrong = [
        (table, column, data_type)
        for table in TABLES
        for column, (data_type, _) in columns[table].items()
        if column.endswith("_at") and data_type != "timestamp with time zone"
    ]

    assert wrong == []


def test_every_text_column_has_a_limit(columns, checks):
    """VARCHAR carries its limit; TEXT needs a CHECK on its length."""
    unbounded = [
        (table, column)
        for table in TABLES
        for column, (data_type, limit) in columns[table].items()
        if (data_type == "character varying" and limit is None)
        or (
            data_type == "text"
            and not any(
                column in definition and "length" in definition
                for definition in checks.get(table, [])
            )
        )
    ]

    assert unbounded == []


def test_money_is_whole_paise_with_its_currency(columns, checks):
    money = [
        (table, column)
        for table in TABLES
        for column in columns[table]
        if column.endswith("_paise")
    ]
    not_bigint = [(t, c) for t, c in money if columns[t][c][0] != "bigint"]
    no_currency = {
        (t, c)
        for t, c in money
        if not any("currency" in d and "'INR'" in d for d in checks.get(t, []))
    }

    assert len(money) >= 7
    assert not_bigint == []
    assert no_currency == PAISE_WITHOUT_CURRENCY


def test_no_postgres_enum_types():
    """Allowed values are a CHECK, which a migration can change in place."""
    assert (
        rows(
            "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public' AND t.typtype = 'e'"
        )
        == []
    )


def test_every_table_has_an_id_and_its_times(columns):
    missing = {
        (table, column)
        for table in TABLES
        for column in ("id", "created_at", "updated_at")
        if column not in columns[table]
    }
    expected = (
        {(t, "id") for t in OWNER_KEYED_TABLES}
        | {(t, "updated_at") for t in APPEND_ONLY_TABLES}
        | {(t, "created_at") for t in NO_CREATED_AT}
    )

    assert missing == expected


# --- section 3: integrity ---------------------------------------------------------------


def test_every_relationship_chooses_what_a_delete_does():
    """NO ACTION is the default nobody chose; every key says CASCADE,
    RESTRICT or SET NULL."""
    unchosen = rows(
        "SELECT c.relname, k.conname FROM pg_constraint k "
        "JOIN pg_class c ON c.oid = k.conrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND k.contype = 'f' AND k.confdeltype = 'a'"
    )

    assert (
        rows(
            "SELECT count(*) FROM pg_constraint k JOIN pg_namespace n "
            "ON n.oid = k.connamespace WHERE n.nspname = 'public' AND k.contype = 'f'"
        )[0][0]
        >= 30
    )
    assert unchosen == []


def test_append_only_tables_refuse_every_change():
    sealed: dict[str, set[str]] = {}
    for table, event in rows(
        "SELECT event_object_table, event_manipulation FROM information_schema.triggers "
        "WHERE trigger_schema = 'public'"
    ):
        sealed.setdefault(table, set()).add(event)
    for table in rows(
        "SELECT tgrelid::regclass::text FROM pg_trigger "
        "WHERE NOT tgisinternal AND tgname LIKE '%no_truncate'"
    ):
        sealed.setdefault(table[0], set()).add("TRUNCATE")

    assert {
        t for t, events in sealed.items() if events >= {"UPDATE", "DELETE", "TRUNCATE"}
    } == SEALED_TABLES


def test_every_rule_in_the_database_is_broken_by_some_test():
    """database.md section 3: each CHECK and UNIQUE has a test that writes the
    forbidden row and watches it refused.

    This is a name check: it proves each rule is named by a test, and the
    convention (pytest.raises(IntegrityError, match=<name>)) makes a named rule
    a broken one. It cannot prove the test is right; review does that.
    """
    named = rows(
        "SELECT c.relname, k.conname FROM pg_constraint k "
        "JOIN pg_class c ON c.oid = k.conrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND k.contype IN ('c', 'u')"
    )
    here = pathlib.Path(__file__).resolve()
    tests = "".join(
        path.read_text(encoding="utf-8")
        for path in here.parent.rglob("*.py")
        if path != here and "__pycache__" not in path.parts
    )

    def rule(table: str, name: str) -> str:
        # Tests name a rule by the words after its prefix: "pitch_length".
        for prefix in (f"ck_{table}_", f"uq_{table}_"):
            name = name.removeprefix(prefix)
        return name

    untested = sorted(
        name
        for table, name in named
        if name not in UNBREAKABLE_ALONE and rule(table, name) not in tests
    )

    assert len(named) > 150
    assert untested == []


# --- section 5: indexes -----------------------------------------------------------------


def test_every_foreign_key_is_indexed():
    """An index whose first column is the key, so deleting a parent row, or
    joining from it, never scans the child table (a unique constraint counts).
    Three were missing, and one had only an index limited to open rows,
    until item 98 (14 October 2026)."""
    keys = set(
        rows(
            "SELECT c.relname, a.attname FROM pg_constraint k "
            "JOIN pg_class c ON c.oid = k.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = k.conkey[1] "
            "WHERE n.nspname = 'public' AND k.contype = 'f'"
        )
    )
    # A partial index serves the key only when it leaves out nothing but
    # NULLs: one limited to open reports cannot find a closed one.
    leading = {
        (table, column)
        for table, column, predicate in rows(
            "SELECT t.relname, a.attname, pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0] "
            "WHERE n.nspname = 'public'"
        )
        if predicate is None or predicate == f"({column} IS NOT NULL)"
    }

    assert len(keys) >= 30
    assert keys - leading == set()
