"""Counter-offers on a quote (item 44, D-123): the rules, and the record both sides read.

On a waiting application (submitted, shortlisted, or an invitation not yet
answered) either side names a figure; the other accepts, declines, or names
its own, which replaces the open one (choice 1A). Each side makes at most
MAX_OFFERS_PER_SIDE on one application. Once one is accepted the figure is
agreed: it pre-fills the memo (`deal_memo.service`), which stays the
contract, and a different fee there is shown beside it (choice 2A).
Negotiation then closes; later changes go through the memo's change request.

The deal moves on only once the figure is settled: accepting the
application, or the invitation, is refused while an offer is open
(`campaigns.service.move_application`), so nobody can say afterwards which
price was agreed. Saying no to the application closes the open offer.

Every write locks the application's row first, as moving it and erasing an
account do, so two offers, an offer and an answer, or an offer and a status
move run one at a time. The partial unique index `uq_quote_offer_one_open`
is the database's own guard on one open offer.

Threat model (security.md section 4): only the two parties reach an offer
(`dependencies.get_visible_application`, 404 to anyone else); answering is
the other side's move and withdrawing the maker's, checked under the
offer's lock; a block, a takedown, a suspension or a deletion ends the
negotiation as it ends anything new between them; a note is plain text
with its flags worked out on read; a daily ceiling and the cap per side stop
anyone grinding the other down by volume (trust-and-safety.md rule 2).
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import brand_is_unavailable, is_unavailable
from app.modules.campaigns import offer_rules as rules
from app.modules.campaigns.exceptions import (
    ApplicationNotFound,
    CampaignNotOpen,
    OfferNotFound,
    OfferOpen,
    OffersClosed,
)
from app.modules.campaigns.models import Application, Campaign
from app.modules.campaigns.offer_models import QuoteOffer
from app.modules.campaigns.schemas import ApplicationRead, to_application_read
from app.modules.notifications import service as notifications
from app.modules.safety.blocks import blocked_between
from app.modules.safety.exceptions import ContentWithheld, OwnContentWithheld
from app.modules.safety.takedowns import campaign_is_withheld, is_withheld

# The statuses still waiting on an answer, the only ones open to offers.
WAITING = frozenset({"submitted", "shortlisted", "invited"})

EXPORTED_TABLES = frozenset({"quote_offer"})
EXPORT_FIELDS = allow(
    "id",
    "application_id",
    "side",
    "amount_paise",
    "currency",
    "note",
    "made_at",
    "outcome",
    "answered_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class OfferSummary:
    """What a read of an application shows of its negotiation."""

    open_offer: QuoteOffer | None
    agreed_amount_paise: int | None


NO_OFFERS = OfferSummary(open_offer=None, agreed_amount_paise=None)


def summaries_for(
    db: Session, application_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, OfferSummary]:
    """Each application's open offer and agreed figure, in one query for any number."""
    ids = set(application_ids)
    if not ids:
        return {}
    found: dict[uuid.UUID, OfferSummary] = {}
    for offer in db.scalars(
        select(QuoteOffer).where(
            QuoteOffer.application_id.in_(ids),
            QuoteOffer.outcome.is_(None) | (QuoteOffer.outcome == "accepted"),
        )
    ):
        current = found.get(offer.application_id, NO_OFFERS)
        if offer.outcome is None:
            current = OfferSummary(offer, current.agreed_amount_paise)
        else:
            current = OfferSummary(current.open_offer, offer.amount_paise)
        found[offer.application_id] = current
    return {
        application_id: found.get(application_id, NO_OFFERS) for application_id in ids
    }


def summary_for(db: Session, application_id: uuid.UUID) -> OfferSummary:
    return summaries_for(db, [application_id])[application_id]


def history(db: Session, application: Application) -> list[QuoteOffer]:
    """Every offer on the application, oldest first: at most 2 x MAX_OFFERS_PER_SIDE."""
    return list(
        db.scalars(
            select(QuoteOffer)
            .where(QuoteOffer.application_id == application.id)
            .order_by(QuoteOffer.made_at, QuoteOffer.id)
        ).all()
    )


def make_offer(
    db: Session,
    application: Application,
    side: str,
    amount_paise: int,
    note: str | None,
    now: datetime,
) -> QuoteOffer:
    """Name a figure on a waiting application, replacing the other side's open one. Commits.

    Raises OffersClosed (not waiting, a barter campaign, or the other side
    is gone),
    CampaignNotOpen, ApplicationNotFound (blocked either way, read as not
    found), ContentWithheld or OwnContentWithheld, OfferAlreadyAgreed,
    OfferLimitReached (MAX_OFFERS_PER_SIDE made already) and OfferOpen (its
    own offer still waits: withdraw it first).
    """
    campaign = _locked_and_negotiable(db, application, side)
    offers = history(db, application)
    refused = rules.refusal_to_make(offers, side)
    if refused is not None:
        db.rollback()
        raise refused()
    # The other side's open offer, if any: a counter replaces it.
    open_offer = next((offer for offer in offers if offer.outcome is None), None)
    if open_offer is not None:
        _end(open_offer, "replaced", now)
    offer = QuoteOffer(
        application_id=application.id,
        side=side,
        amount_paise=amount_paise,
        note=note,
        made_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(offer)
    try:
        db.flush()
    except IntegrityError:
        # The database's own rule: one open offer an application.
        db.rollback()
        raise OfferOpen() from None
    _tell(
        db,
        application,
        campaign,
        to=_other(side),
        kind="offer_received",
        offer=offer,
        now=now,
    )
    db.commit()
    db.refresh(offer)
    return offer


def accept(
    db: Session, application: Application, offer_id: uuid.UUID, side: str, now: datetime
) -> QuoteOffer:
    """The other side agrees the figure. Commits.

    Raises what make_offer raises for a negotiation that is closed, and
    OfferNotFound, OfferAnswered and OfferNotYours.
    """
    campaign = _locked_and_negotiable(db, application, side)
    offer = _answerable(db, application, offer_id, side)
    _end(offer, "accepted", now)
    _tell(
        db,
        application,
        campaign,
        to=offer.side,
        kind="offer_accepted",
        offer=offer,
        now=now,
    )
    db.commit()
    db.refresh(offer)
    return offer


def decline(
    db: Session, application: Application, offer_id: uuid.UUID, side: str, now: datetime
) -> QuoteOffer:
    """The other side says no; the application waits on, as it was. Commits.

    Saying no needs nothing else open: like rejecting or declining, it is
    never refused for a closed campaign. Raises OfferNotFound, OfferAnswered
    and OfferNotYours.
    """
    _lock(db, application)
    offer = _answerable(db, application, offer_id, side)
    _end(offer, "declined", now)
    campaign = db.get_one(Campaign, application.campaign_id)
    _tell(
        db,
        application,
        campaign,
        to=offer.side,
        kind="offer_declined",
        offer=offer,
        now=now,
    )
    db.commit()
    db.refresh(offer)
    return offer


def withdraw(
    db: Session, application: Application, offer_id: uuid.UUID, side: str, now: datetime
) -> QuoteOffer:
    """Its maker takes an open offer back. Commits.

    Raises OfferNotFound, OfferAnswered and OfferNotYours (the other side's offer).
    """
    _lock(db, application)
    offer = _locked_offer(db, application, offer_id)
    refused = rules.refusal_to_withdraw(offer, side)
    if refused is not None:
        db.rollback()
        raise refused()
    _end(offer, "withdrawn", now)
    campaign = db.get_one(Campaign, application.campaign_id)
    _tell(
        db,
        application,
        campaign,
        to=_other(side),
        kind="offer_withdrawn",
        offer=offer,
        now=now,
    )
    db.commit()
    db.refresh(offer)
    return offer


def has_open(db: Session, application_id: uuid.UUID) -> bool:
    """True while an offer waits. Read under the application's lock by its caller."""
    return (
        db.scalar(
            select(QuoteOffer.id).where(
                QuoteOffer.application_id == application_id, QuoteOffer.outcome.is_(None)
            )
        )
        is not None
    )


def close_open(
    db: Session, application_ids: Iterable[uuid.UUID], actor: str | None, now: datetime
) -> None:
    """End the open offers of applications that are ending. Never commits.

    The actor's own offer is withdrawn and the other side's declined, as if
    each had been answered; with no actor (an account leaving, D-122) every
    one is withdrawn. Nobody is told: the move that ends the application
    tells them already. Called under the applications' locks.
    """
    ids = list(application_ids)
    if not ids:
        return
    for offer_side in ("brand", "creator"):
        outcome = "withdrawn" if actor in (None, offer_side) else "declined"
        db.execute(
            update(QuoteOffer)
            .where(
                QuoteOffer.application_id.in_(ids),
                QuoteOffer.side == offer_side,
                QuoteOffer.outcome.is_(None),
            )
            .values(outcome=outcome, answered_at=now, updated_at=now)
        )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Every offer on an application of this account's, made by either side."""
    application_ids = select(Application.id).where(
        Application.creator_id.in_(
            select(Creator.id).where(Creator.account_id == account_id)
        )
        | Application.campaign_id.in_(
            select(Campaign.id)
            .join(Brand, Brand.id == Campaign.brand_id)
            .where(Brand.account_id == account_id)
        )
    )
    offers = list(
        db.scalars(
            select(QuoteOffer)
            .where(QuoteOffer.application_id.in_(application_ids))
            .order_by(QuoteOffer.made_at, QuoteOffer.id)
        ).all()
    )
    return [
        build_section(
            "quote_offers",
            table="quote_offer",
            purpose=(
                "Figures you and the other side offered each other on an "
                "application before a deal, and how each was answered. "
                "`side` says who offered it."
            ),
            objects=offers,
            fields=EXPORT_FIELDS,
        )
    ]


def _other(side: str) -> str:
    return "creator" if side == "brand" else "brand"


def _lock(db: Session, application: Application) -> None:
    db.refresh(application, attribute_names=["status"], with_for_update=True)


def _locked_and_negotiable(db: Session, application: Application, side: str) -> Campaign:
    """Lock the application, then refuse a negotiation that cannot go on."""
    _lock(db, application)
    if application.status not in WAITING:
        db.rollback()
        raise OffersClosed()
    campaign = db.get_one(Campaign, application.campaign_id)
    if campaign.status != "open" or brand_is_unavailable(db, campaign.brand_id):
        db.rollback()
        raise CampaignNotOpen()
    if campaign.campaign_type == "barter":
        db.rollback()
        raise OffersClosed(
            "A barter campaign pays in goods: there is no figure to offer."
        )
    brand_account_id = db.scalar(
        select(Brand.account_id).where(Brand.id == campaign.brand_id)
    )
    creator_account_id = db.scalar(
        select(Creator.account_id).where(Creator.id == application.creator_id)
    )
    if creator_account_id is None or is_unavailable(db, creator_account_id):
        db.rollback()
        raise OffersClosed()
    if brand_account_id is not None and blocked_between(
        db, brand_account_id, creator_account_id
    ):
        # Blocked either way (item 59): not found, so the block stays private.
        db.rollback()
        raise ApplicationNotFound()
    # Withheld (item 52): nothing new reaches a withheld item, or comes from one.
    own, theirs = ("campaign", "creator") if side == "brand" else ("creator", "campaign")
    withheld = {
        "campaign": campaign_is_withheld(db, campaign.id, campaign.brand_id),
        "creator": is_withheld(db, "creator", application.creator_id),
    }
    if withheld[own]:
        db.rollback()
        raise OwnContentWithheld()
    if withheld[theirs]:
        db.rollback()
        raise ContentWithheld()
    return campaign


def _locked_offer(
    db: Session, application: Application, offer_id: uuid.UUID
) -> QuoteOffer:
    offer = db.scalars(
        select(QuoteOffer)
        .where(QuoteOffer.id == offer_id, QuoteOffer.application_id == application.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if offer is None:
        db.rollback()
        raise OfferNotFound()
    return offer


def _answerable(
    db: Session, application: Application, offer_id: uuid.UUID, side: str
) -> QuoteOffer:
    offer = _locked_offer(db, application, offer_id)
    refused = rules.refusal_to_answer(offer, side)
    if refused is not None:
        db.rollback()
        raise refused()
    return offer


def _end(offer: QuoteOffer, outcome: str, now: datetime) -> None:
    offer.outcome = outcome
    offer.answered_at = now
    offer.updated_at = now


def _tell(
    db: Session,
    application: Application,
    campaign: Campaign,
    *,
    to: str,
    kind: str,
    offer: QuoteOffer,
    now: datetime,
) -> None:
    """Tell one side, in the same transaction as the change itself."""
    if to == "brand":
        account_id = db.scalar(
            select(Brand.account_id).where(Brand.id == campaign.brand_id)
        )
    else:
        account_id = db.scalar(
            select(Creator.account_id).where(Creator.id == application.creator_id)
        )
    if account_id is None:
        return
    notifications.record(
        db,
        account_id=account_id,
        notification_type=kind,
        now=now,
        campaign_id=campaign.id,
        application_id=application.id,
        details={
            "campaign_title": campaign.title,
            "offer_id": str(offer.id),
            "amount_paise": offer.amount_paise,
        },
    )


def read_applications(
    db: Session, applications: list[Application]
) -> list[ApplicationRead]:
    """Applications as the API returns them, their offers in one query for all."""
    summaries = summaries_for(db, [application.id for application in applications])
    return [
        to_application_read(
            application,
            summaries[application.id].open_offer,
            summaries[application.id].agreed_amount_paise,
        )
        for application in applications
    ]


def read_application(db: Session, application: Application) -> ApplicationRead:
    [read] = read_applications(db, [application])
    return read
