"""How long each kind of report may wait for an answer (item 51, D-103).

The Intermediary Rules, 2021, as amended on 10 February 2026 (in force
20 February 2026), set the clocks a platform keeps to stay protected from
liability for what its users post (IT Act section 79; legal.md section 3.3):

- every complaint is acknowledged within 24 hours. Ours is acknowledged the
  moment it is filed: the answer to the request, and a `report_received`
  notification carrying the time it will be answered by;
- a complaint about content that exposes, shows sexually, or **impersonates**
  the person complaining is acted on within 2 hours (rule 3(2)(b), cut from
  24): `impersonation` and `intimate_content`;
- a complaint about content the rules prohibit (rule 3(1)(b): harassing,
  defamatory, misleading, impersonating another person, and the rest) within
  36 hours (cut from 72): `abuse`, `fake_profile`, `spam` and `other`, any of
  which may be such content;
- every other grievance is resolved within 7 days (cut from 15):
  `non_payment`, a dispute about a deal rather than about content.

Where a category could fall under two clocks it takes the shorter, so the
safe mistake is answering too early. Which category falls under which clock
is our reading of the rules, marked **Confirm** for the lawyer in legal.md
section 3.3; changing it is a change to this one table, and a report keeps
the deadline it was given when it was filed.

Pure: no database, no clock of its own. The time is always passed in.
"""

from datetime import datetime, timedelta

from app.modules.auth.models.account import REPORT_CATEGORIES

TWO_HOURS = timedelta(hours=2)
THIRTY_SIX_HOURS = timedelta(hours=36)
SEVEN_DAYS = timedelta(days=7)

ANSWER_WITHIN: dict[str, timedelta] = {
    "impersonation": TWO_HOURS,
    "intimate_content": TWO_HOURS,
    "abuse": THIRTY_SIX_HOURS,
    "fake_profile": THIRTY_SIX_HOURS,
    "spam": THIRTY_SIX_HOURS,
    "other": THIRTY_SIX_HOURS,
    "non_payment": SEVEN_DAYS,
}

# The longest clock. The database refuses a deadline later than this after
# filing (ck_report_due_within_seven_days), whatever the code does.
LONGEST = SEVEN_DAYS

# How long before a deadline the admins are warned.
DUE_SOON = timedelta(minutes=30)


def check_clocks(clocks: dict[str, timedelta], categories: tuple[str, ...]) -> None:
    """Refuse to start on a category without a clock, or a clock past 7 days."""
    if set(clocks) != set(categories):
        # A category without a clock would be a report nobody has to answer.
        raise RuntimeError(
            "Every report category needs a clock in report_clocks.ANSWER_WITHIN: "
            f"missing {sorted(set(categories) - set(clocks))}, "
            f"unknown {sorted(set(clocks) - set(categories))}"
        )
    if max(clocks.values()) > LONGEST:
        raise RuntimeError("A report clock is longer than the law's longest, 7 days")


check_clocks(ANSWER_WITHIN, REPORT_CATEGORIES)


def due_at(category: str, filed_at: datetime) -> datetime:
    """When a report of this category, filed at `filed_at`, must be answered."""
    return filed_at + ANSWER_WITHIN[category]


def is_late(due: datetime, resolved_at: datetime | None, now: datetime) -> bool:
    """Answered after its deadline, or still open past it.

    Answered exactly at the deadline is in time: the rules give "within".
    """
    answered_or_now = resolved_at if resolved_at is not None else now
    return answered_or_now > due
