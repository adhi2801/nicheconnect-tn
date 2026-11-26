"""A limit on how long something may take, as a whole (item 118, D-186).

A connect or read timeout bounds one wait; nothing bounds the sum of them.
A server that sends one byte just inside each read timeout keeps a call
alive for ever, and retries multiply every wait by their number. A
`Deadline` is fixed once, when the call or the job's run starts, and each
wait inside it is cut to the time left, as Google's SRE book sets a deadline
high in the stack and passes it down rather than inventing one per hop.

Counted on `time.monotonic`, which never jumps when the machine's wall clock
is corrected; the clock is passed in, so tests move time without sleeping
(testing.md section 5). Pure: no input or output, nothing global.
"""

import time
from collections.abc import Callable

Clock = Callable[[], float]


class DeadlinePassed(TimeoutError):
    """A whole call's limit passed. The message names what was being done, nothing else."""


class Deadline:
    """The moment a call or a run must be finished by."""

    __slots__ = ("_clock", "_ends_at")

    def __init__(self, seconds: float, clock: Clock = time.monotonic) -> None:
        if seconds < 0:
            raise ValueError("a limit cannot be negative")
        self._clock = clock
        self._ends_at = clock() + seconds

    def remaining(self) -> float:
        """Seconds left, never below 0."""
        return max(0.0, self._ends_at - self._clock())

    def expired(self) -> bool:
        """True from the moment the limit is reached."""
        return self._clock() >= self._ends_at

    def capped(self, seconds: float | None) -> float:
        """The smaller of `seconds` and the time left; no limit (None) is the time left."""
        left = self.remaining()
        return left if seconds is None else min(seconds, left)
