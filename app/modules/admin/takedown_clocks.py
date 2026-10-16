"""When a takedown must be done by, and whether it was late (item 52, D-104).

The IT Rules, as amended on 10 February 2026 (in force 20 February 2026),
give a platform **3 hours** from receiving a court order, or a government
notice from an authorised officer, to remove or disable access to what it
names (rule 3(1)(d); legal.md section 3.3). The clock runs from when the
order reached us, which the admin reads from the order, not from when
someone got round to recording it; the moment it was withheld is the
server's, so a takedown can never be made to look on time.

A takedown on a report keeps the report's own deadline (report_clocks.py).

Pure: no database, no clock of its own. The time is always passed in.
"""

from datetime import datetime, timedelta

ORDER_WITHIN = timedelta(hours=3)
# How long before the takedown an order may say it reached us. A mistyped
# year must not make a late takedown look on time; the database holds the
# same line (ck_takedown_received_before_withheld).
OLDEST_ORDER = timedelta(days=30)


def order_due_at(received_at: datetime) -> datetime:
    """When an order received at `received_at` must be acted on."""
    return received_at + ORDER_WITHIN


def is_late(due: datetime, withheld_at: datetime) -> bool:
    """Withheld after its deadline. Exactly at it is in time: the rules say "within"."""
    return withheld_at > due
