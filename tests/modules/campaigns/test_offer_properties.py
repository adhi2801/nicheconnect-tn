"""What holds for every sequence of moves in a negotiation (item 44, D-123).

Hypothesis plays random moves by both sides through the pure rules
(`offer_rules`), applying each allowed one as `offer_service` does, and
checks after every move that the negotiation stays sound: one offer open
at most, no side past its cap, one figure agreed at most, and nothing
offered once it is. The service's own tests prove it follows these rules.
"""

from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from app.modules.campaigns.exceptions import OfferOpen
from app.modules.campaigns.offer_models import MAX_OFFERS_PER_SIDE, OFFER_SIDES
from app.modules.campaigns.offer_rules import (
    refusal_to_answer,
    refusal_to_make,
    refusal_to_withdraw,
)


@dataclass
class Offer:
    side: str
    outcome: str | None = None


ACTIONS = ("make", "accept", "decline", "withdraw")
moves = st.lists(
    st.tuples(st.sampled_from(ACTIONS), st.sampled_from(OFFER_SIDES)), max_size=40
)


def play(sequence: list[tuple[str, str]]) -> list[list[Offer]]:
    """Apply each allowed move as the service would; every state along the way."""
    offers: list[Offer] = []
    states = []
    for action, side in sequence:
        open_offer = next((offer for offer in offers if offer.outcome is None), None)
        if action == "make":
            if refusal_to_make(offers, side) is None:
                if open_offer is not None:
                    open_offer.outcome = "replaced"
                offers.append(Offer(side))
        elif open_offer is not None:
            refusal = (
                refusal_to_withdraw(open_offer, side)
                if action == "withdraw"
                else refusal_to_answer(open_offer, side)
            )
            if refusal is None:
                open_offer.outcome = {
                    "accept": "accepted",
                    "decline": "declined",
                    "withdraw": "withdrawn",
                }[action]
        states.append([Offer(offer.side, offer.outcome) for offer in offers])
    return states


@given(moves)
def test_at_most_one_offer_is_ever_open(sequence):
    for offers in play(sequence):
        assert sum(1 for offer in offers if offer.outcome is None) <= 1


@given(moves)
def test_no_side_ever_makes_more_than_its_share(sequence):
    for offers in play(sequence):
        for side in OFFER_SIDES:
            assert sum(1 for offer in offers if offer.side == side) <= MAX_OFFERS_PER_SIDE


@given(moves)
def test_at_most_one_figure_is_agreed_and_it_is_the_last_offer(sequence):
    for offers in play(sequence):
        agreed = [i for i, offer in enumerate(offers) if offer.outcome == "accepted"]
        assert len(agreed) <= 1
        if agreed:
            # Nothing is offered once a figure is agreed, and nothing stays open.
            assert agreed[0] == len(offers) - 1


@given(moves)
def test_an_offer_is_never_answered_by_its_maker(sequence):
    """Replayed with the rule's own answer: accepting your own offer is refused."""
    for offers in play(sequence):
        for offer in offers:
            if offer.outcome is None:
                assert refusal_to_answer(offer, offer.side) is not None


@given(st.lists(st.sampled_from(OFFER_SIDES), max_size=8), st.sampled_from(OFFER_SIDES))
def test_the_other_sides_open_offer_never_stops_a_counter(history, side):
    """A counter replaces the open offer; only one's own open offer blocks."""
    other = "creator" if side == "brand" else "brand"
    offers = [Offer(maker, "declined") for maker in history] + [Offer(other)]

    assert refusal_to_make(offers, side) is not OfferOpen


@given(
    st.sampled_from(OFFER_SIDES),
    st.sampled_from(["accepted", "declined", "replaced", "withdrawn"]),
)
def test_an_ended_offer_cannot_be_answered_or_withdrawn(side, outcome):
    offer = Offer("brand", outcome)

    assert refusal_to_answer(offer, side) is not None
    assert refusal_to_withdraw(offer, side) is not None


@given(st.lists(st.sampled_from(OFFER_SIDES), max_size=4), st.sampled_from(OFFER_SIDES))
def test_ones_own_open_offer_always_stops_another(history, side):
    """Below the cap and with nothing agreed, one's own open offer blocks a new one."""
    offers = [Offer(maker, "declined") for maker in history if maker != side] + [
        Offer(side)
    ]

    assert refusal_to_make(offers, side) is OfferOpen
