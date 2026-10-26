"""When feedback on a deal may be given, and when it may be seen (item 77, D-136). Pure.

Either side of a finished deal (paid and confirmed, or barter with its work
approved) may answer once, within FEEDBACK_WINDOW of the deal finishing.
Neither side's answer is seen, by the other side or anyone, until both have
answered or the window has closed: nobody answers knowing what was said
about them, so nobody answers to retaliate.
"""

from datetime import datetime, timedelta

FEEDBACK_WINDOW = timedelta(days=14)
# The three questions, each 1 to 5, read for whoever is answered about:
# - brief: followed the brief (a creator) / gave a clear brief (a brand);
# - reliability: delivered on time (a creator) / paid as agreed (a brand);
# - easy: easy to work with.
SCORES: tuple[str, ...] = ("brief", "reliability", "easy")
SCORE_MIN, SCORE_MAX = 1, 5
# Below this many revealed answers, an average is not shown (D-038's floor).
MIN_ANSWERS = 3


def window_ends(finished_at: datetime) -> datetime:
    return finished_at + FEEDBACK_WINDOW


def may_answer(
    finished_at: datetime | None, already_answered: bool, now: datetime
) -> str | None:
    """None when this side may answer now, else why not."""
    if finished_at is None:
        return "not_finished"
    if already_answered:
        return "already_given"
    if now >= window_ends(finished_at):
        return "closed"
    return None


def revealed(other_side_answered: bool, window_ends_at: datetime, now: datetime) -> bool:
    """Whether an answer may be seen: the other side answered too, or time ran out."""
    return other_side_answered or now >= window_ends_at
