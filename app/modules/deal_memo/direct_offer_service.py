"""Direct offers: a creator's memo to a brand not on the platform (D-189).

The creator sends the terms and the brand's name and number, and gets a
link to send the brand. The brand opens it, asks for a code to that number,
and accepts with its name, an email and the code: one transaction then makes
its account and profile, a hidden campaign and application, and the memo,
agreed by both, its record opening with the creator's proposal and the
brand's acceptance. After that the deal is an ordinary deal, on the paths
every deal already takes.

Threat model (security.md section 4, STRIDE):

- **Spoofing**: only the holder of the number the creator typed can accept;
  the code is a login code, under the phone's own caps on sending and
  guessing (security.md section 1), and the link alone accepts nothing.
- **Tampering**: the terms' fingerprint is fixed when the offer is sent; an
  offer cannot be changed, only withdrawn, and the brand accepts by naming
  that fingerprint, which the memo's own fingerprint must equal.
- **Repudiation**: the proposal and the acceptance are both sealed on the
  deal record, the second naming how it was proven (a phone code).
- **Information disclosure**: the link shows the creator's public name and
  the terms, nothing else; the link's token is kept only as an HMAC; the
  number and the name are erased when the offer ends; whether a number has
  a brand account is said only after its own code was right.
- **Denial of service**: rate limits on every route, the phone's code caps,
  10 offers a Tamil Nadu day per creator and 3 a week to one number.
- **Elevation of privilege**: accepting makes an ordinary brand account, on
  a number that has none, after the checks a second side on a number takes
  (D-126); never on an admin's number, a suspended side or a moving one.

Locks, in the order every path takes them, so nothing can wait in a circle
(40P01 would be a 500): the brand's phone (the login's advisory lock), then
the creator's row, then the offer's row. Erasing a creator takes their
phone, their row, then their applications and offers; sending takes the
creator's row, then the number's advisory lock. Every refusal after a lock
rolls back before it raises.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.config import settings
from app.core.errors import DomainError
from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
)
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.core.taxonomy import CURRENCY
from app.db.refusals import constraint_name
from app.modules.auth import attribution_service as attribution
from app.modules.auth import phone_changes, sides, suspension
from app.modules.auth import service as login
from app.modules.auth.attribution_service import Arrival
from app.modules.auth.exceptions import PhoneChangeWaiting
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import (
    DIRECT_CAMPAIGN_TYPE,
    DIRECT_ORIGIN,
    Application,
    Campaign,
)
from app.modules.deal_memo import direct_offer_notices as notices
from app.modules.deal_memo import direct_offer_rules as rules
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.direct_offer_models import (
    DIRECT_OFFER_LIFETIME,
    ENDED_OFFER_KEPT_FOR,
    DirectOffer,
)
from app.modules.deal_memo.exceptions import (
    BrandAccountExists,
    CreatorLeft,
    DirectOfferAlreadyAccepted,
    DirectOfferDailyLimit,
    DirectOfferExpired,
    DirectOfferNotFound,
    DirectOfferNumberLimit,
    DirectOfferOwnNumber,
    DirectOffersOff,
    DirectOfferStopped,
    DirectOfferStoppedByRecipient,
    DirectOfferTermsMismatch,
    DirectOfferWithdrawn,
    DueDateHasPassed,
    DueDateTooFar,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.notifications import service as notifications
from app.modules.profiles import brand_name_service
from app.modules.profiles.exceptions import EmailTaken, MustBeAnAdult
from app.modules.profiles.profile_service import is_adult

# Tables this module answers for in a data export.
EXPORTED_TABLES = frozenset({"direct_offer"})

# The memo's terms version the offer's fingerprint is made under (D-127,
# D-140): the one every new memo is made with.
TERMS_VERSION = 3
# The terms an offer carries, exactly a memo's (record_service.TERMS_FIELDS
# and `draft_review`).
TERM_FIELDS: tuple[str, ...] = (*record.TERMS_FIELDS, "draft_review")
# The hidden campaign's title: what a deal list shows where a campaign's
# title would be.
DIRECT_CAMPAIGN_TITLE = "Direct offer"
# How a brand that arrived by a direct offer is counted (D-080), within the
# sources that exist: no new source without a schema change.
ARRIVAL = Arrival(source="other", campaign_tag="direct-offer")
# How many offers the job empties or deletes in one transaction.
JOB_BATCH = 1000

EXPORT_FIELDS = allow(
    "id",
    "status",
    "brand_name",
    "deliverables",
    "deliverable_items",
    "fee_amount_paise",
    "currency",
    "cancellation_fee_paise",
    "approval_window_days",
    "payment_due_days",
    "usage_rights_days",
    "content_due_on",
    "disclosure_required",
    "draft_review",
    "extra_terms",
    "terms_sha256",
    "expires_at",
    "opened_at",
    "ended_at",
    "deal_memo_id",
    "created_at",
    "updated_at",
)


def ensure_on() -> None:
    """Refuse every direct offer route while the feature is off (DirectOffersOff).

    On only with the switch and real notice wording: a placeholder can
    never be served, whatever the switch says (constraint 6).
    """
    if not (settings.direct_offers_enabled and notices.wording_ready()):
        raise DirectOffersOff()


def terms_sha256(values: dict[str, Any], items: list[dict[str, Any]]) -> str:
    """The fingerprint the deal record will seal these terms under."""
    return record.fingerprint_of_terms(values, items, TERMS_VERSION)


def _offer_terms(offer: DirectOffer) -> dict[str, Any]:
    return {field: getattr(offer, field) for field in TERM_FIELDS}


# Why an offer no longer waits, as each shown status answers it.
ENDED_ERRORS: dict[str, type[DomainError]] = {
    "accepted": DirectOfferAlreadyAccepted,
    "withdrawn": DirectOfferWithdrawn,
    "stopped": DirectOfferStopped,
    "expired": DirectOfferExpired,
}


def _ended_error(offer: DirectOffer, now: datetime) -> DomainError | None:
    """Why the offer can no longer be accepted or withdrawn, or None."""
    shown = rules.shown_status(offer.status, offer.expires_at, now)
    if shown == "sent":
        return None
    return ENDED_ERRORS[shown]()


def _ensure_waiting(db: Session, offer: DirectOffer, now: datetime) -> None:
    error = _ended_error(offer, now)
    if error is not None:
        db.rollback()
        raise error


# --- the creator's side -------------------------------------------------------


@dataclass(frozen=True)
class SentOffer:
    offer: DirectOffer
    link_token: str


def send(
    db: Session, creator: Creator, fields: dict[str, Any], now: datetime
) -> SentOffer:
    """Send a direct offer to the number in `fields`, and return its link's token.

    The creator's row is locked first, so their offers are counted one at a
    time against the day's 10; then the number, by an advisory lock on its
    keyed hash, so offers from anyone are counted one at a time against its
    week's 3. Raises DueDateHasPassed, DueDateTooFar, CreatorLeft,
    DirectOfferOwnNumber, DirectOfferStoppedByRecipient, DirectOfferDailyLimit
    and DirectOfferNumberLimit (each 429 with Retry-After).
    """
    ensure_on()
    problem = rules.due_date_problem(fields["content_due_on"], now)
    if problem == "passed":
        raise DueDateHasPassed()
    if problem == "too_far":
        raise DueDateTooFar()

    db.scalars(
        select(Creator)
        .where(Creator.id == creator.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).one()
    own_phone = db.scalar(select(Account.phone).where(Account.id == creator.account_id))
    if own_phone is None:
        # Deleted meanwhile (D-122): nothing new starts with someone who left.
        db.rollback()
        raise CreatorLeft()
    phone: str = fields.pop("brand_phone")
    if phone == own_phone:
        db.rollback()
        raise DirectOfferOwnNumber()
    phone_hash = rules.hash_recipient_phone(phone)
    stopped = db.scalar(
        select(DirectOffer.id).where(
            DirectOffer.creator_id == creator.id,
            DirectOffer.recipient_phone_hash == phone_hash,
            DirectOffer.status == "stopped",
        )
    )
    if stopped is not None:
        db.rollback()
        raise DirectOfferStoppedByRecipient()
    today = db.scalar(
        select(func.count(DirectOffer.id)).where(
            DirectOffer.creator_id == creator.id,
            DirectOffer.created_at >= rules.start_of_india_day(now),
        )
    )
    if (today or 0) >= rules.DAILY_OFFERS_PER_CREATOR:
        db.rollback()
        raise DirectOfferDailyLimit(
            headers={"Retry-After": str(rules.seconds_until_tomorrow(now))}
        )

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"direct-offer-number:{phone_hash}"},
    )
    this_week = sorted(
        db.scalars(
            select(DirectOffer.created_at).where(
                DirectOffer.recipient_phone_hash == phone_hash,
                DirectOffer.created_at > now - rules.NUMBER_WINDOW,
            )
        ).all()
    )
    if len(this_week) >= rules.WEEKLY_OFFERS_PER_NUMBER:
        db.rollback()
        oldest = this_week[len(this_week) - rules.WEEKLY_OFFERS_PER_NUMBER]
        raise DirectOfferNumberLimit(
            headers={"Retry-After": str(rules.seconds_until_number_frees(oldest, now))}
        )

    token = rules.new_link_token()
    fields["currency"] = CURRENCY
    items = [dict(item) for item in fields.pop("deliverable_items")]
    offer = DirectOffer(
        creator_id=creator.id,
        token_hash=rules.hash_link_token(token),
        recipient_phone_hash=phone_hash,
        recipient_phone=phone,
        deliverable_items=items,
        terms_sha256=terms_sha256(fields, items),
        status="sent",
        expires_at=now + DIRECT_OFFER_LIFETIME,
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return SentOffer(offer=offer, link_token=token)


def list_mine(
    db: Session, creator: Creator, *, limit: int, cursor: str | None = None
) -> Slice[DirectOffer]:
    """The creator's offers, newest first, a page at a time. One query."""
    query = select(DirectOffer).where(DirectOffer.creator_id == creator.id)
    if cursor is not None:
        query = query.where(
            older_than_cursor(DirectOffer.created_at, DirectOffer.id, cursor)
        )
    rows = list(
        db.scalars(
            query.order_by(DirectOffer.created_at.desc(), DirectOffer.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda row: (row.created_at, row.id))


def get_mine(db: Session, creator: Creator, offer_id: uuid.UUID) -> DirectOffer:
    """One of the creator's own offers. Anyone else's is DirectOfferNotFound."""
    offer = db.scalars(
        select(DirectOffer).where(
            DirectOffer.id == offer_id, DirectOffer.creator_id == creator.id
        )
    ).first()
    if offer is None:
        raise DirectOfferNotFound()
    return offer


def _end(offer: DirectOffer, status: str, now: datetime) -> None:
    """End an offer as `status`, erasing the number and the name with it."""
    offer.status = status
    offer.ended_at = offer.ended_at or now
    offer.recipient_phone = None
    offer.brand_name = None
    offer.updated_at = now


def withdraw(db: Session, offer: DirectOffer, now: datetime) -> DirectOffer:
    """Take back an offer still waiting. Locked first, so an acceptance at the
    same moment lands wholly before (and this is refused) or after (and it
    finds the offer withdrawn). Raises the ended errors."""
    _lock(db, offer)
    _ensure_waiting(db, offer, now)
    _end(offer, "withdrawn", now)
    db.commit()
    db.refresh(offer)
    return offer


def _lock(db: Session, offer: DirectOffer) -> None:
    db.scalars(
        select(DirectOffer)
        .where(DirectOffer.id == offer.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


# --- the link -----------------------------------------------------------------


@dataclass(frozen=True)
class LinkView:
    offer: DirectOffer
    creator: Creator


def _find_by_token(db: Session, token: str) -> LinkView:
    """The offer a link's token opens, with its creator, while the creator's
    account stands. Anything else is DirectOfferNotFound, all alike. One query."""
    if not rules.is_link_token(token):
        raise DirectOfferNotFound()
    found = db.execute(
        select(DirectOffer, Creator)
        .join(Creator, Creator.id == DirectOffer.creator_id)
        .where(
            DirectOffer.token_hash == rules.hash_link_token(token),
            suspension.account_is_active(Creator.account_id),
        )
    ).first()
    if found is None:
        raise DirectOfferNotFound()
    return LinkView(offer=found[0], creator=found[1])


def open_link(db: Session, token: str, now: datetime) -> LinkView:
    """What the brand sees at the link, while the offer waits.

    The first opening is noted for the creator's list, in one statement
    that only an unopened offer matches. Raises DirectOfferNotFound and the
    ended errors, so a link that no longer works says why.
    """
    ensure_on()
    view = _find_by_token(db, token)
    _ensure_waiting(db, view.offer, now)
    if view.offer.opened_at is None:
        db.execute(
            update(DirectOffer)
            .where(DirectOffer.id == view.offer.id, DirectOffer.opened_at.is_(None))
            .values(opened_at=now, updated_at=now)
        )
        db.commit()
        db.refresh(view.offer)
    return view


def link_notice() -> str:
    """The notice the link page shows. Served only once it is real wording."""
    ensure_on()
    return notices.LINK_PAGE_NOTICE


def request_code(db: Session, token: str, now: datetime) -> login.PendingOtp:
    """A code to the offer's number, through the login's own code and caps.

    Raises DirectOfferNotFound, the ended errors, and OtpSendLimitReached.
    """
    ensure_on()
    view = _find_by_token(db, token)
    _ensure_waiting(db, view.offer, now)
    phone = cast("str", view.offer.recipient_phone)
    return login.request_otp(db, phone, now)


def stop(db: Session, token: str, now: datetime) -> None:
    """ "Stop these": this creator may send this number nothing more.

    No account is needed: the link proves the number's holder received it.
    The offer ends as `stopped`, its number and name erased; its keyed hash
    stays as the block. Allowed on a waiting, withdrawn or expired offer;
    a second tap changes nothing. Raises DirectOfferNotFound and
    DirectOfferAlreadyAccepted.
    """
    ensure_on()
    if not rules.is_link_token(token):
        raise DirectOfferNotFound()
    offer = db.scalars(
        select(DirectOffer)
        .where(DirectOffer.token_hash == rules.hash_link_token(token))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if offer is None:
        db.rollback()
        raise DirectOfferNotFound()
    if offer.status == "accepted":
        db.rollback()
        raise DirectOfferAlreadyAccepted()
    if offer.status != "stopped":
        _end(offer, "stopped", now)
    db.commit()


@dataclass(frozen=True)
class Acceptance:
    login: login.LoginResult
    memo: DealMemo


def accept(db: Session, token: str, fields: dict[str, Any], now: datetime) -> Acceptance:
    """The brand accepts: account, profile, hidden campaign and application,
    and the memo agreed by both, in one transaction, then signed in.

    `fields` holds `brand_name`, `email`, `date_of_birth`, `code` and
    `terms_sha256`. The code is checked first, under the phone's lock and
    caps; every refusal after it leaves the code unused. Raises
    DirectOfferNotFound, the ended errors, OtpVerifyLimitReached, OtpInvalid,
    DirectOfferTermsMismatch, DueDateHasPassed, BrandAccountExists,
    DirectOfferOwnNumber, PhoneChangeWaiting, RoleMismatch, AccountSuspended,
    MustBeAnAdult, EmailTaken and BrandNameNeedsDomain (item 75).
    """
    ensure_on()
    view = _find_by_token(db, token)
    _ensure_waiting(db, view.offer, now)
    phone = cast("str", view.offer.recipient_phone)
    challenge = login.check_phone_code(db, phone, fields["code"], now)

    # The creator, then the offer, each read again under its lock.
    creator = db.scalars(
        select(Creator)
        .where(
            Creator.id == view.creator.id,
            suspension.account_is_active(Creator.account_id),
        )
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).first()
    if creator is None:
        db.rollback()
        raise DirectOfferNotFound()
    offer = view.offer
    _lock(db, offer)
    _ensure_waiting(db, offer, now)
    if offer.recipient_phone != phone:  # pragma: no cover - ended above
        db.rollback()
        raise DirectOfferNotFound()
    if fields["terms_sha256"] != offer.terms_sha256:
        db.rollback()
        raise DirectOfferTermsMismatch()
    if offer.content_due_on < india_date(now):
        db.rollback()
        raise DueDateHasPassed()
    _ensure_number_may_hold_a_brand(db, phone, creator)
    if not is_adult(fields["date_of_birth"], india_date(now)):
        db.rollback()
        raise MustBeAnAdult()

    account, brand = _make_brand(db, phone, fields, now)
    memo, campaign_id = _make_deal(db, offer, creator, brand, now)
    _end(offer, "accepted", now)
    offer.deal_memo_id = memo.id
    # The creator hears as a brand does when its memo is accepted.
    notifications.record(
        db,
        account_id=creator.account_id,
        notification_type="memo_accepted",
        now=now,
        campaign_id=campaign_id,
        application_id=memo.application_id,
        details={"campaign_title": DIRECT_CAMPAIGN_TITLE},
    )
    challenge.consumed_at = now
    result = login.issue_session(db, account, uuid.uuid4(), now)
    db.commit()
    db.refresh(memo)
    return Acceptance(login=result, memo=memo)


def _ensure_number_may_hold_a_brand(db: Session, phone: str, creator: Creator) -> None:
    """Refuse a brand account on this number where login would, and more.

    A number with a brand account already makes none (D-189 makes a new
    brand, never joins one); the creator's own number never deals with
    itself (D-126); a number an account waits to move onto, an admin's, a
    suspended side's or a moving side's makes none, as at login.
    """
    on_number = sides.on_number(db, phone)
    if any(found.id == creator.account_id for found in on_number):
        db.rollback()
        raise DirectOfferOwnNumber()
    if any(found.role == "brand" for found in on_number):
        db.rollback()
        raise BrandAccountExists()
    if not on_number and phone_changes.is_waiting_to_move(db, phone):
        db.rollback()
        raise PhoneChangeWaiting()
    if on_number:
        login.ensure_second_side_allowed(db, on_number)


def _make_brand(
    db: Session, phone: str, fields: dict[str, Any], now: datetime
) -> tuple[Account, Brand]:
    """The brand's account and profile, as login and profile creation make them.

    Adults only (D-086), checked by the caller; only the time of the
    confirmation is kept. Raises EmailTaken and BrandNameNeedsDomain.
    """
    email: str = fields["email"]
    if db.scalar(select(Brand.id).where(Brand.email == email)) is not None:
        db.rollback()
        raise EmailTaken()
    account = Account(phone=phone, role="brand", adult_confirmed_at=now)
    db.add(account)
    db.flush()
    attribution.record_arrival(db, account, ARRIVAL, now)
    brand = Brand(
        account_id=account.id,
        name=fields["brand_name"],
        email=email,
        created_at=now,
        updated_at=now,
    )
    db.add(brand)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if constraint_name(error) == "uq_brand_email":
            raise EmailTaken() from error
        raise
    # Item 75: a name that reads as a protected brand's is held, as it is
    # from publishing a campaign; at a link no domain can be proven yet.
    brand_name_service.ensure_may_publish(db, brand.id)
    return account, brand


def _make_deal(
    db: Session, offer: DirectOffer, creator: Creator, brand: Brand, now: datetime
) -> tuple[DealMemo, uuid.UUID]:
    """The hidden campaign and application, the memo and its two sealed entries."""
    campaign = Campaign(
        brand_id=brand.id,
        title=DIRECT_CAMPAIGN_TITLE,
        description="",
        campaign_type=DIRECT_CAMPAIGN_TYPE,
        # Closed from the start: it takes no creator, so it reaches no
        # discovery, matching, alert or city figure (applying.taking_creators).
        status="closed",
        cities=[creator.city],
        niches=list(creator.niches),
        deliverables=offer.deliverables,
        created_at=now,
        updated_at=now,
    )
    db.add(campaign)
    db.flush()
    application = Application(
        campaign_id=campaign.id,
        creator_id=creator.id,
        origin=DIRECT_ORIGIN,
        status="accepted",
        quoted_amount_paise=offer.fee_amount_paise,
        status_changed_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(application)
    db.flush()
    memo = DealMemo(
        application_id=application.id,
        terms_version=TERMS_VERSION,
        status="accepted",
        sent_at=offer.created_at,
        accepted_at=now,
        created_at=now,
        updated_at=now,
        **{field: getattr(offer, field) for field in (*TERM_FIELDS, "currency")},
    )
    db.add(memo)
    db.flush()
    memos.replace_deliverables(db, memo.id, list(offer.deliverable_items), now)
    db.refresh(memo, attribute_names=["deliverable_items"])
    if record.terms_fingerprint(memo) != offer.terms_sha256:
        # The memo must hold exactly the terms the brand accepted; a drift
        # here is a bug, and nothing of it may be committed.
        db.rollback()
        raise RuntimeError("A direct offer's memo does not hold its terms")
    facts = record.terms_facts(memo)
    record.append(
        db,
        memo,
        kind="direct_offer_proposed",
        actor_role="creator",
        now=now,
        occurred_at=offer.created_at,
        facts=facts,
    )
    record.append(
        db,
        memo,
        kind="direct_offer_accepted",
        actor_role="brand",
        now=now,
        facts={**facts, "proven_by": "phone_code"},
    )
    return memo, campaign.id


# --- the job, the export and erasure ------------------------------------------


@dataclass(frozen=True)
class JobRun:
    expired: int
    deleted: int


def expire_and_erase(db: Session, now: datetime) -> JobRun:
    """Empty offers whose 14 days ran out, and delete those that ended without
    a deal 30 days ago. Commits; safe to run twice.

    An expired offer's number and name are erased in the statement that
    marks it expired. An offer an acceptance holds is skipped (SKIP LOCKED),
    and found accepted by the next run. Stopped offers stay: each is the
    block its number's holder asked for.
    """
    waiting = (
        select(DirectOffer.id)
        .where(DirectOffer.status == "sent", DirectOffer.expires_at <= now)
        .limit(JOB_BATCH)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    expired = cast(
        "CursorResult[Any]",
        db.execute(
            update(DirectOffer)
            .where(DirectOffer.id.in_(waiting))
            .values(
                status="expired",
                ended_at=DirectOffer.expires_at,
                recipient_phone=None,
                brand_name=None,
                updated_at=now,
            )
        ),
    ).rowcount
    old = (
        select(DirectOffer.id)
        .where(
            DirectOffer.status.in_(("withdrawn", "expired")),
            DirectOffer.ended_at <= now - ENDED_OFFER_KEPT_FOR,
        )
        .limit(JOB_BATCH)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    deleted = cast(
        "CursorResult[Any]",
        db.execute(delete(DirectOffer).where(DirectOffer.id.in_(old))),
    ).rowcount
    db.commit()
    return JobRun(expired=expired, deleted=deleted)


def erase_for_creator(db: Session, creator_id: uuid.UUID) -> None:
    """Delete a departing creator's offers that never became a deal (D-122).

    The erasure holds the creator's row, which every acceptance reads under
    a lock first, so none lands meanwhile. Offers that became deals stay,
    their number and name already erased, as deal history. Never commits.
    """
    db.execute(
        delete(DirectOffer).where(
            DirectOffer.creator_id == creator_id, DirectOffer.status != "accepted"
        )
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The creator's offers, or the brand's one that became its deal. Two queries.

    Never the number or any hash: the number is the brand's, given by the
    creator; the hashes are keys, not data about anyone.
    """
    creator_id = db.scalar(select(Creator.id).where(Creator.account_id == account_id))
    if creator_id is not None:
        query = select(DirectOffer).where(DirectOffer.creator_id == creator_id)
    else:
        query = (
            select(DirectOffer)
            .join(DealMemo, DealMemo.id == DirectOffer.deal_memo_id)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .join(Brand, Brand.id == Campaign.brand_id)
            .where(Brand.account_id == account_id)
        )
    offers = list(
        db.scalars(
            query.order_by(DirectOffer.created_at, DirectOffer.id).limit(
                MAX_ROWS_PER_SECTION + 1
            )
        ).all()
    )
    return [
        build_section(
            "direct_offers",
            table="direct_offer",
            purpose=(
                "Direct offers a creator sent a brand not yet on the platform "
                "(D-189): the terms, the brand's name while it waited, when it "
                "was opened and how it ended. The brand's number is never here: "
                "it is erased when an offer ends."
            ),
            objects=offers,
            fields=EXPORT_FIELDS,
        )
    ]
