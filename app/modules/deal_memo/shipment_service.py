"""A barter deal's shipment, on the record (item 68, D-131): the rules.

The brand records the courier and the tracking number once the deal is
agreed (`ship`); until the creator says the goods arrived it may correct a
mistyped number, each version sealed as its own `product_shipped` entry,
so a correction is on the record too. Only the creator says they arrived
(`receive`), once, sealed as `product_received`; after that neither side
changes anything. Each step is written under the deal's lock with its
record entry, and the other side is told.

Threat model: only the deal's brand ships and only its creator receives
(`dependencies.get_brand_memo` and `get_creator_memo`, 404 to anyone
else); a tracking number is shown as text and never fetched, so it cannot
be used to send anyone to a look-alike page; the record seals the number's
fingerprint, and `unchanged` shows a row rewritten behind the app's back.
An agreed deal carries on across a block (item 59), so its shipment does.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.exceptions import (
    ShipmentAlreadyReceived,
    ShipmentClosed,
    ShipmentNotFound,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.service import memos_for_account, notify_party
from app.modules.deal_memo.shipment_models import BarterShipment

EXPORTED_TABLES = frozenset({"barter_shipment"})
EXPORT_FIELDS = allow(
    "id",
    "deal_memo_id",
    "carrier",
    "tracking_number",
    "shipped_at",
    "received_at",
    "created_at",
    "updated_at",
)


def of(db: Session, memo: DealMemo) -> BarterShipment:
    """The deal's shipment. Raises ShipmentNotFound."""
    shipment = _shipment(db, memo)
    if shipment is None:
        raise ShipmentNotFound()
    return shipment


def ship(
    db: Session, memo: DealMemo, *, carrier: str, tracking_number: str, now: datetime
) -> BarterShipment:
    """Record or correct how the goods were sent, seal it, tell the creator. Commits.

    The same courier and number again changes nothing. Raises ShipmentClosed
    (not an agreed barter deal) and ShipmentAlreadyReceived.
    """
    db.refresh(memo, attribute_names=["status"], with_for_update=True)
    if memo.status != "accepted" or _campaign_type(db, memo) != "barter":
        db.rollback()
        raise ShipmentClosed()
    shipment = _shipment(db, memo)
    if shipment is not None and shipment.received_at is not None:
        db.rollback()
        raise ShipmentAlreadyReceived()
    if shipment is not None and (shipment.carrier, shipment.tracking_number) == (
        carrier,
        tracking_number,
    ):
        db.rollback()
        return shipment
    if shipment is None:
        shipment = BarterShipment(
            deal_memo_id=memo.id,
            carrier=carrier,
            tracking_number=tracking_number,
            shipped_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(shipment)
    else:
        shipment.carrier = carrier
        shipment.tracking_number = tracking_number
        shipment.shipped_at = now
        shipment.updated_at = now
    db.flush()
    record.append(
        db,
        memo,
        kind="product_shipped",
        actor_role="brand",
        now=now,
        facts={
            "shipment_id": str(shipment.id),
            "carrier": carrier,
            "tracking_sha256": record.fingerprint(tracking_number),
        },
    )
    notify_party(db, memo, to="creator", notification_type="product_shipped", now=now)
    db.commit()
    db.refresh(shipment)
    return shipment


def receive(db: Session, memo: DealMemo, now: datetime) -> BarterShipment:
    """The creator says the goods arrived; sealed, and the brand told. Commits.

    Raises ShipmentNotFound and ShipmentAlreadyReceived.
    """
    db.refresh(memo, attribute_names=["status"], with_for_update=True)
    shipment = _shipment(db, memo)
    if shipment is None:
        db.rollback()
        raise ShipmentNotFound()
    if shipment.received_at is not None:
        db.rollback()
        raise ShipmentAlreadyReceived()
    shipment.received_at = now
    shipment.updated_at = now
    record.append(
        db,
        memo,
        kind="product_received",
        actor_role="creator",
        now=now,
        facts={"shipment_id": str(shipment.id)},
    )
    notify_party(db, memo, to="brand", notification_type="product_received", now=now)
    db.commit()
    db.refresh(shipment)
    return shipment


def unchanged(db: Session, memo: DealMemo) -> bool | None:
    """Whether the shipment still matches what was last sealed for it. None: none.

    Two queries.
    """
    shipment = _shipment(db, memo)
    last = db.scalars(
        select(DealRecordEntry.facts)
        .where(
            DealRecordEntry.deal_memo_id == memo.id,
            DealRecordEntry.kind == "product_shipped",
        )
        .order_by(DealRecordEntry.sequence.desc())
        .limit(1)
    ).first()
    if shipment is None and last is None:
        return None
    return (
        shipment is not None
        and last is not None
        and last["shipment_id"] == str(shipment.id)
        and last["carrier"] == shipment.carrier
        and last["tracking_sha256"] == record.fingerprint(shipment.tracking_number)
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The shipments on this account's deals, the brand's and the creator's alike."""
    memo_ids = {
        memo.id
        for memo in memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)
    }
    shipments = (
        list(
            db.scalars(
                select(BarterShipment)
                .where(BarterShipment.deal_memo_id.in_(memo_ids))
                .order_by(BarterShipment.created_at, BarterShipment.id)
            ).all()
        )
        if memo_ids
        else []
    )
    return [
        build_section(
            "barter_shipments",
            table="barter_shipment",
            purpose=(
                "How the goods on your barter deals were sent, and when the "
                "creator said they arrived, each sealed onto the deal's record."
            ),
            objects=shipments,
            fields=EXPORT_FIELDS,
        )
    ]


def _shipment(db: Session, memo: DealMemo) -> BarterShipment | None:
    # Read after the deal's own lock (`ship`, `receive`), which orders every
    # step of a deal, so it is the latest committed.
    return db.scalars(
        select(BarterShipment)
        .where(BarterShipment.deal_memo_id == memo.id)
        .execution_options(populate_existing=True)
    ).first()


def _campaign_type(db: Session, memo: DealMemo) -> str:
    return db.scalars(
        select(Campaign.campaign_type)
        .join(Application, Application.campaign_id == Campaign.id)
        .where(Application.id == memo.application_id)
    ).one()
