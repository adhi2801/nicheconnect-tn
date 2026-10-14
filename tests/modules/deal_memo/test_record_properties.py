"""The deal record's fingerprint and Merkle proofs, for any input (D-090).

The record is only worth anything if anyone can recompute it (D-057): the
same facts must always give the same bytes, whatever order they were built
in, and every proof must check against its root while a changed leaf fails.
"""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.deal_memo import merkle
from app.modules.deal_memo.record_service import canonical

# What may go on the record: strings, whole numbers, booleans, null, and
# lists and string-keyed objects of them. No floats (D-057).
facts = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=20),
    lambda inner: (
        st.lists(inner, max_size=4)
        | st.dictionaries(st.text(max_size=8), inner, max_size=4)
    ),
    max_leaves=20,
)


def reordered(item):
    """The same facts, every object's keys inserted in reverse."""
    if isinstance(item, dict):
        return {key: reordered(item[key]) for key in reversed(list(item))}
    if isinstance(item, list):
        return [reordered(each) for each in item]
    return item


@given(facts)
def test_the_same_facts_give_the_same_bytes_whatever_their_order(value):
    assert canonical(reordered(value)) == canonical(value)


@given(facts)
def test_the_bytes_read_back_as_the_facts(value):
    assert json.loads(canonical(value).decode("utf-8")) == value


@given(facts)
def test_there_is_one_spelling_compact_with_keys_sorted(value):
    """RFC 8785's bytes, for the values the record allows."""
    expected = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    assert canonical(value) == expected.encode("utf-8")


@given(facts, st.floats(allow_nan=False))
def test_a_float_anywhere_is_refused(value, number):
    with pytest.raises(TypeError):
        canonical({"facts": value, "nested": [{"amount": number}]})


leaves = st.lists(st.binary(min_size=1, max_size=48), min_size=1, max_size=40)


@given(leaves, st.data())
def test_every_leafs_proof_checks_against_the_root(found, data):
    index = data.draw(st.integers(min_value=0, max_value=len(found) - 1))
    path = merkle.audit_path(index, found)

    assert merkle.root_from_path(index, len(found), found[index], path) == (
        merkle.root(found)
    )


@given(leaves, st.data(), st.binary(min_size=1, max_size=48))
def test_a_changed_leaf_does_not_check(found, data, other):
    index = data.draw(st.integers(min_value=0, max_value=len(found) - 1))
    if other == found[index]:
        return
    path = merkle.audit_path(index, found)

    assert merkle.root_from_path(index, len(found), other, path) != merkle.root(found)


@given(st.lists(st.binary(min_size=1, max_size=48), min_size=2, max_size=40), st.data())
def test_a_proof_claimed_for_another_place_does_not_check(found, data):
    index, claimed = data.draw(
        st.lists(
            st.integers(min_value=0, max_value=len(found) - 1),
            min_size=2,
            max_size=2,
            unique=True,
        )
    )
    path = merkle.audit_path(index, found)
    try:
        result = merkle.root_from_path(claimed, len(found), found[index], path)
    except ValueError:
        return  # refused outright: the path has the wrong length for that place
    assert result != merkle.root(found) or found[index] == found[claimed]
