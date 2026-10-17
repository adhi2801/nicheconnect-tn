"""A code is bound to one change: what holds for every action and value (item 82)."""

import re

from hypothesis import assume, given
from hypothesis import strategies as st

from app.modules.auth.models.step_up_challenge import STEP_UP_ACTIONS, VALUE_HASH_PATTERN
from app.modules.auth.step_up_service import value_hash

actions = st.sampled_from(STEP_UP_ACTIONS)
values = st.text(max_size=130)


@given(action=actions, value=values)
def test_the_hash_is_what_the_database_accepts(action, value):
    assert re.fullmatch(VALUE_HASH_PATTERN, value_hash(action, value))


@given(action=actions, value=values)
def test_the_same_change_always_gives_the_same_hash(action, value):
    assert value_hash(action, value) == value_hash(action, value)


@given(first=st.tuples(actions, values), second=st.tuples(actions, values))
def test_two_different_changes_never_share_a_hash(first, second):
    """So a code asked for one UPI ID, or one action, cannot allow another."""
    assume(first != second)

    assert value_hash(*first) != value_hash(*second)


@given(value=values)
def test_the_action_is_bound_even_when_the_values_could_run_together(value):
    """No action and value can pass for another action: the separator holds."""
    for action in STEP_UP_ACTIONS:
        for other in STEP_UP_ACTIONS:
            if action != other:
                assert value_hash(action, value) != value_hash(other, value)
