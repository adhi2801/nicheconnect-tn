"""The campaign report over HTTP (item 47, D-088). Rules live in `report_service`."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import report_csv
from app.modules.campaigns.dependencies import OwnedCampaign
from app.modules.campaigns.report_schemas import (
    CampaignReportRead,
    ReportCreatorRead,
    ReportDealRead,
    ReportNumbersRead,
    ReportResultsRead,
    ReportSealRead,
    ReportTotalsRead,
)
from app.modules.campaigns.report_service import (
    CampaignReport,
    DealLine,
    Results,
    build_report,
)
from app.modules.campaigns.schemas import ApplicationCountsRead

# A report reads every deal on a campaign: asked for now and then, not
# polled, so a tighter limit than an ordinary read.
REPORT_LIMIT = "20 per minute"
# Private business figures that change with every step of a deal: never kept
# by a browser or a proxy.
NO_STORE = "no-store"

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brand accounts can do this"),
    404: problem_doc("No such campaign, or it is not yours"),
    409: problem_doc("The brand profile has not been created yet"),
    422: problem_doc("The campaign id is not a valid id"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{campaign_id}/report",
    response_model=CampaignReportRead,
    summary="A campaign report to hand on",
    description=(
        "For the owning brand: every deal on the campaign (drafts left out) "
        "with its creator, terms, delivery, approval, payment, the results "
        "read from its screenshots, and the deal record's latest seal, plus "
        "totals. Worked out as of now, never stored. Results are read from "
        "screenshots, never verified. The same as a spreadsheet: "
        "`/report.csv`."
    ),
    responses=_ERRORS,
)
@rate_limit(REPORT_LIMIT)
def campaign_report(
    request: Request,
    response: Response,
    campaign: OwnedCampaign,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CampaignReportRead:
    response.headers["Cache-Control"] = NO_STORE
    return _read(build_report(db, campaign, now))


@router.get(
    "/{campaign_id}/report.csv",
    summary="A campaign report as a spreadsheet",
    description=(
        "The campaign report's deals as CSV, one row per deal, for Excel, "
        "Google Sheets or Numbers: UTF-8 with a byte-order mark, money in "
        "rupees, Tamil Nadu dates, and any cell a spreadsheet would run as a "
        "formula written with a leading apostrophe. Saved as a file. The "
        "owning brand only."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "The report as CSV, one row per deal",
        },
        **_ERRORS,
    },
)
@rate_limit(REPORT_LIMIT)
def campaign_report_csv(
    request: Request,
    campaign: OwnedCampaign,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    report = build_report(db, campaign, now)
    return Response(
        report_csv.render(report),
        media_type="text/csv; charset=utf-8",
        headers={
            "Cache-Control": NO_STORE,
            "Content-Disposition": (
                f'attachment; filename="{report_csv.filename(report)}"'
            ),
        },
    )


def _results(results: Results) -> ReportResultsRead:
    return ReportResultsRead(
        readings=results.readings,
        readings_marked_wrong=results.readings_marked_wrong,
        includes_abbreviated=results.includes_abbreviated,
        numbers=ReportNumbersRead(**results.numbers),
    )


def _deal(line: DealLine) -> ReportDealRead:
    memo, payment = line.memo, line.payment
    return ReportDealRead(
        deal_memo_id=memo.id,
        creator=ReportCreatorRead(
            display_name=line.creator_display_name, handle=line.creator_handle
        ),
        stage=line.stage.stage,
        waiting_on=line.stage.waiting_on,
        has_open_dispute=line.stage.has_open_dispute,
        deliverables=memo.deliverables,
        content_due_on=memo.content_due_on,
        work_due_on=line.stage.work_due_on,
        fee_amount_paise=memo.fee_amount_paise,
        accepted_on=india_date(memo.accepted_at) if memo.accepted_at else None,
        first_submitted_on=line.first_submitted_on,
        delivered_on_time=line.delivered_on_time,
        approved_on=line.approved_on,
        approved_by_clock=line.approved_by_clock,
        content_url=line.content_url,
        disclosure_confirmed=line.disclosure_confirmed,
        payment_state=line.payment_state,
        payment_due_on=payment.due_on if payment else None,
        payment_marked_paid_on=(
            india_date(payment.marked_paid_at)
            if payment and payment.marked_paid_at
            else None
        ),
        payment_confirmed_on=(
            india_date(payment.confirmed_at) if payment and payment.confirmed_at else None
        ),
        paid_on_time=line.paid_on_time,
        results=_results(line.results),
        record=ReportSealRead(
            intact=line.seal.intact,
            entries=line.seal.entries,
            latest_seal=line.seal.latest_seal,
            stamped_on=line.seal.stamped_on,
        ),
    )


def _read(report: CampaignReport) -> CampaignReportRead:
    totals = report.totals
    return CampaignReportRead(
        campaign_id=report.campaign.id,
        title=report.campaign.title,
        status=report.campaign.status,
        campaign_type=report.campaign.campaign_type,
        generated_at=report.generated_at,
        totals=ReportTotalsRead(
            applications=ApplicationCountsRead(**totals.applications),
            deals=totals.deals,
            deals_agreed=totals.deals_agreed,
            deals_finished=totals.deals_finished,
            barter_deals_agreed=totals.barter_deals_agreed,
            agreed_value_paise=totals.agreed_value_paise,
            marked_paid_paise=totals.marked_paid_paise,
            confirmed_paise=totals.confirmed_paise,
            deliveries_judged=totals.deliveries_judged,
            delivered_on_time=totals.delivered_on_time,
            payments_sent=totals.payments_sent,
            payments_sent_on_time=totals.payments_sent_on_time,
            results=_results(totals.results),
            records_intact=totals.records_intact,
        ),
        deals=[_deal(line) for line in report.deals],
    )
