"""Every CHECK in the models is the CHECK the migrations made (database.md section 3).

`alembic check` compares tables, columns, indexes and keys, but not CHECK
constraints, so a rule changed in a model and not in a migration, or the
other way round, passed every gate until 10 October 2026. The models are what
a reader trusts; the migrated database is what actually refuses a row.

This builds every table from the models in a scratch schema, inside a
transaction that is rolled back, and compares each CHECK with the migrated
one as PostgreSQL itself prints them, so spelling differences that mean the
same thing do not count, and differences that change the rule do.
"""

import pytest
from sqlalchemy import text

import app.db.models  # noqa: F401 - registers every table, as the app does
from app.db.base import Base
from app.db.session import engine

SCRATCH = "model_check"
CHECKS = text(
    """
    SELECT c.relname, k.conname, pg_get_constraintdef(k.oid)
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE k.contype = 'c' AND n.nspname = :schema
    """
)


def normalised(definition: str) -> str:
    # Two migrations written in September wrote LIKE 'https://%%', escaping a
    # percent sign that needed no escape. In LIKE, two wildcards in a row
    # match exactly what one does, so the rule is the same; a migration to
    # respell it would rewrite nothing.
    return definition.replace("%%", "%")


@pytest.fixture(scope="module")
def both() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f"CREATE SCHEMA {SCRATCH}"))
            Base.metadata.create_all(
                connection.execution_options(schema_translate_map={None: SCRATCH})
            )
            from_models = {
                (table, name): normalised(definition)
                for table, name, definition in connection.execute(
                    CHECKS, {"schema": SCRATCH}
                )
            }
            migrated = {
                (table, name): normalised(definition)
                for table, name, definition in connection.execute(
                    CHECKS, {"schema": "public"}
                )
                if table in Base.metadata.tables
            }
        finally:
            transaction.rollback()
    return from_models, migrated


def test_the_comparison_sees_the_checks(both):
    from_models, migrated = both
    # If the queries broke, every comparison below would pass on nothing.
    assert len(from_models) > 100
    assert ("application", "ck_application_status_allowed") in migrated


def test_every_check_in_the_models_was_migrated(both):
    from_models, migrated = both

    assert sorted(set(from_models) - set(migrated)) == []


def test_every_migrated_check_is_in_the_models(both):
    from_models, migrated = both

    assert sorted(set(migrated) - set(from_models)) == []


def test_each_check_says_the_same_in_both(both):
    from_models, migrated = both

    differ = {
        key: {"models": from_models[key], "database": migrated[key]}
        for key in from_models.keys() & migrated.keys()
        if from_models[key] != migrated[key]
    }

    assert differ == {}
