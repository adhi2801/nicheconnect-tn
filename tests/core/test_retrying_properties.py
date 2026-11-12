"""What holds for every run of the retry loop (item 118, D-186; testing.md section 6).

Whatever fails, however long each try takes, and whatever the jitter draws:
never more tries than allowed, no try given longer than its own limit or the
time the call has left, and nothing begun after the whole limit.
"""

from contextlib import suppress

from hypothesis import given
from hypothesis import strategies as st

from app.core.deadline import Deadline
from app.core.retrying import full_jitter_pause, within_tries


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Curable(Exception):
    pass


class Incurable(Exception):
    pass


outcomes = st.lists(
    st.sampled_from(["answer", "curable", "incurable"]), min_size=1, max_size=8
)
durations = st.lists(
    st.floats(min_value=0, max_value=200, allow_nan=False), min_size=8, max_size=8
)


@given(
    outcomes=outcomes,
    durations=durations,
    tries=st.integers(min_value=1, max_value=5),
    limit=st.floats(min_value=0.1, max_value=300, allow_nan=False),
    try_limit=st.floats(min_value=0.1, max_value=120, allow_nan=False),
    jitter=st.floats(min_value=0, max_value=0.999, allow_nan=False),
)
def test_the_loop_keeps_every_limit(outcomes, durations, tries, limit, try_limit, jitter):
    clock = Clock()
    deadline = Deadline(limit, clock)
    started: list[tuple[float, float]] = []

    def send(seconds: float) -> str:
        n = len(started)
        started.append((clock.now, seconds))
        clock.now += min(durations[n], seconds)  # a try never outlives its own limit
        outcome = outcomes[min(n, len(outcomes) - 1)]
        if outcome == "curable":
            raise Curable
        if outcome == "incurable":
            raise Incurable
        return "answer"

    def sleep(seconds: float) -> None:
        assert seconds >= 0
        clock.now += seconds

    with suppress(Curable, Incurable):
        within_tries(
            send,
            deadline=deadline,
            tries=tries,
            try_limit=try_limit,
            retryable=lambda error: isinstance(error, Curable),
            base_delay=1.0,
            sleep=sleep,
            jitter=lambda: jitter,
        )

    assert 1 <= len(started) <= tries
    for at, seconds in started:
        assert seconds <= try_limit
        assert at < limit or len(started) == 1  # only the first try may start late
        assert seconds <= max(0.0, limit - at)
    # Nothing tried again after an error no try can cure.
    for n in range(len(started) - 1):
        assert outcomes[min(n, len(outcomes) - 1)] == "curable"
    assert clock.now <= max(limit, started[0][0]) + 1e-9


@given(
    attempt=st.integers(min_value=1, max_value=10),
    base=st.floats(min_value=0, max_value=10, allow_nan=False),
    jitter=st.floats(min_value=0, max_value=0.999, allow_nan=False),
)
def test_a_wait_is_never_more_than_its_step(attempt, base, jitter):
    pause = full_jitter_pause(attempt, base, jitter)

    assert 0 <= pause <= base * 2 ** (attempt - 1)
