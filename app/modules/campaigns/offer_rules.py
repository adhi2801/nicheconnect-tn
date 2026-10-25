"""The rules of a negotiation, as pure functions of the offers so far (item 44, D-123).

`offer_service` calls these under the application's lock; here they take
only what they decide on, so tests/modules/campaigns/test_offer_properties.py
can try every sequence of moves without a database. Each returns the error
to raise, or None when the move is allowed.
"""

from collections.abc import Sequence
from typing import Protocol

from app.core.errors import DomainError
from app.modules.campaigns.exceptions import (
    OfferAlreadyAgreed,
    OfferAnswered,
    OfferLimitReached,
    OfferNotYours,
    OfferOpen,
)
from app.modules.campaigns.offer_models import MAX_OFFERS_PER_SIDE


class OfferFacts(Protocol):
    """What the rules read of an offer: who made it, and how it ended."""

    @property
    def side(self) -> str: ...

    @property
    def outcome(self) -> str | None: ...


def refusal_to_make(offers: Sequence[OfferFacts], side: str) -> type[DomainError] | None:
    """Why `side` may not make another offer now, if it may not.

    Once a figure is agreed nothing more is offered; each side makes at most
    MAX_OFFERS_PER_SIDE; a side's own open offer is withdrawn before it
    makes another. The other side's open offer does not stop it: the new
    one replaces it, which is how a counter works.
    """
    if any(offer.outcome == "accepted" for offer in offers):
        return OfferAlreadyAgreed
    if sum(1 for offer in offers if offer.side == side) >= MAX_OFFERS_PER_SIDE:
        return OfferLimitReached
    if any(offer.outcome is None and offer.side == side for offer in offers):
        return OfferOpen
    return None


def refusal_to_answer(offer: OfferFacts, side: str) -> type[DomainError] | None:
    """Why `side` may not accept or decline this offer: answered, or its own."""
    if offer.outcome is not None:
        return OfferAnswered
    if offer.side == side:
        return OfferNotYours
    return None


def refusal_to_withdraw(offer: OfferFacts, side: str) -> type[DomainError] | None:
    """Why `side` may not take this offer back: answered, or the other side's."""
    if offer.outcome is not None:
        return OfferAnswered
    if offer.side != side:
        return OfferNotYours
    return None
