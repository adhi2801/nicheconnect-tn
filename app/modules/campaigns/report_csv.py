"""The campaign report as a spreadsheet: one row per deal (item 47, D-088).

Written for Excel, Google Sheets and Numbers as a person opens them:

- UTF-8 with a byte-order mark, so Excel shows a Tamil name or the rupee
  sign as written instead of guessing an old code page;
- RFC 4180: commas, quotes and line breaks inside a cell are quoted, and
  lines end in CRLF;
- money in rupees with two decimals, worked out from whole paise without a
  float ever being involved;
- **no formula can run.** A cell a spreadsheet would read as a formula
  (starting `=`, `+`, `-`, `@`, a tab or a carriage return) is written with
  a leading apostrophe, as OWASP's CSV injection guidance advises. Creator
  names, deliverables and links are typed by people; without this, a name
  such as `=HYPERLINK(...)` would run on the brand's computer.

Totals are not a row: a spreadsheet sums its own columns, and a totals row
would be summed again by anyone who selects the column.
"""

import csv
import io
from datetime import date

from app.core.clock import india_date
from app.modules.campaigns.report_service import CampaignReport, DealLine
from app.modules.deal_memo.proof_reading_models import READING_METRICS

BYTE_ORDER_MARK = "﻿"
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

COLUMNS: tuple[str, ...] = (
    "creator",
    "handle",
    "stage",
    "waiting_on",
    "open_dispute",
    "deliverables",
    "content_due_on",
    "fee_inr",
    "accepted_on",
    "first_submitted_on",
    "delivered_on_time",
    "approved_on",
    "approved_by_clock",
    "content_url",
    "disclosure_confirmed",
    "payment_state",
    "payment_due_on",
    "marked_paid_on",
    "confirmed_on",
    "paid_on_time",
    *READING_METRICS,
    "readings",
    "readings_marked_wrong",
    "figures_abbreviated",
    "record_intact",
    "record_entries",
    "latest_seal",
    "seal_stamped_on",
    "deal_memo_id",
    # Added by item 27 (D-140), last, so no existing column moves.
    "work_due_on",
)


def rupees(paise: int | None) -> str:
    """Whole paise as rupees with two decimals: 150050 is "1500.50"."""
    if paise is None:
        return ""
    return f"{paise // 100}.{paise % 100:02d}"


def safe_cell(value: str) -> str:
    """A cell no spreadsheet will run as a formula."""
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, date):
        return value.isoformat()
    return safe_cell(str(value))


def _row(line: DealLine) -> list[str]:
    memo, payment = line.memo, line.payment
    values: list[object] = [
        line.creator_display_name,
        line.creator_handle,
        line.stage.stage,
        line.stage.waiting_on,
        line.stage.has_open_dispute,
        memo.deliverables,
        memo.content_due_on,
        rupees(memo.fee_amount_paise),
        india_date(memo.accepted_at) if memo.accepted_at else None,
        line.first_submitted_on,
        line.delivered_on_time,
        line.approved_on,
        line.approved_by_clock,
        line.content_url,
        line.disclosure_confirmed,
        line.payment_state,
        payment.due_on if payment else None,
        india_date(payment.marked_paid_at)
        if payment and payment.marked_paid_at
        else None,
        india_date(payment.confirmed_at) if payment and payment.confirmed_at else None,
        line.paid_on_time,
        *(line.results.numbers[metric] for metric in READING_METRICS),
        line.results.readings,
        line.results.readings_marked_wrong,
        line.results.includes_abbreviated,
        line.seal.intact,
        line.seal.entries,
        line.seal.latest_seal,
        line.seal.stamped_on,
        memo.id,
        line.stage.work_due_on,
    ]
    return [_cell(value) for value in values]


def render(report: CampaignReport) -> str:
    """The report's deals as CSV text, header first, byte-order mark included."""
    out = io.StringIO()
    out.write(BYTE_ORDER_MARK)
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for line in report.deals:
        writer.writerow(_row(line))
    return out.getvalue()


def filename(report: CampaignReport) -> str:
    """ASCII only, so every browser saves it under this name."""
    day = india_date(report.generated_at).isoformat()
    return f"campaign-report-{report.campaign.id.hex[:8]}-{day}.csv"
