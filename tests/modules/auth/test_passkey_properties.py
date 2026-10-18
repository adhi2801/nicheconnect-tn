"""What holds for every counter a key could report (D-113)."""

from hypothesis import given
from hypothesis import strategies as st

from app.modules.auth.passkeys import counter_is_fresh

counters = st.integers(min_value=0, max_value=2**32 - 1)


@given(stored=counters, answered=counters)
def test_a_counting_key_passes_only_by_counting_up(stored, answered):
    if stored == 0 and answered == 0:
        assert counter_is_fresh(stored, answered)
    else:
        assert counter_is_fresh(stored, answered) == (answered > stored)


@given(stored=counters)
def test_a_repeated_counter_is_a_copy_unless_the_key_never_counts(stored):
    assert counter_is_fresh(stored, stored) == (stored == 0)


@given(stored=st.integers(min_value=1, max_value=2**32 - 1))
def test_a_key_that_counted_can_never_fall_back_to_zero(stored):
    assert not counter_is_fresh(stored, 0)
