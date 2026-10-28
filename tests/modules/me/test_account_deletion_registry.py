"""Every table is said to be erased, emptied, held or not personal, exactly once (D-122).

A new table holding personal data cannot slip past deletion: it fails here
until someone decides what happens to it. That each erased table really is
emptied is proven in test_account_deletion_erasure.py.
"""

import pytest

import app.main  # noqa: F401 - every model registered on the metadata
from app.core.config import Settings
from app.db.base import Base
from app.modules.auth import erasure
from app.modules.me import account_deletion_registry as registry
from app.modules.me import export_service

PLACES = {
    "erased": registry.ERASED,
    "emptied": registry.EMPTIED,
    "held": registry.HELD,
    "not personal": frozenset(registry.NOT_PERSONAL),
}


def test_the_tables_are_read():
    assert len(Base.metadata.tables) > 30


def test_every_table_has_a_place():
    placed = frozenset().union(*PLACES.values())

    assert set(Base.metadata.tables) - placed == set()


def test_no_table_has_two_places():
    seen: dict[str, str] = {}
    for place, tables in PLACES.items():
        for table in tables:
            assert table not in seen, f"{table} is both {seen[table]} and {place}"
            seen[table] = place


def test_nothing_placed_is_not_a_table():
    placed = frozenset().union(*PLACES.values())

    assert placed - set(Base.metadata.tables) == set()


def test_auth_erases_and_empties_what_the_registry_says_of_it():
    assert erasure.ERASED_TABLES <= registry.ERASED
    assert erasure.EMPTIED_TABLES == registry.EMPTIED


def test_each_kind_kept_holds_tables_of_its_own():
    kinds = [kind.kind for kind in registry.KEPT]
    assert len(kinds) == len(set(kinds))
    for kind in registry.KEPT:
        assert kind.tables
        for other in registry.KEPT:
            assert other is kind or not (kind.tables & other.tables)


@pytest.mark.parametrize("kind", registry.KEPT, ids=lambda kind: kind.kind)
def test_each_kind_has_its_setting_unset_until_the_law_is_known(kind):
    field = Settings.model_fields[kind.setting]

    assert field.default is None
    assert kind.kept_for_days() is None


def test_nothing_not_personal_is_in_the_export():
    """What holds nothing about a person is not handed to them either."""
    for table in registry.NOT_PERSONAL:
        assert table in export_service.NOT_EXPORTED
