"""Every brand route, against every role in a brand (item 13, D-148).

Denied by default, proven mechanically, as `test_agent_scopes.py` proves an
assistant's token: a route counts as a brand route when it acts for a brand
through the one check (`auth.brand_dependencies`), by the Brand-Id header or
through the deal or application in its path. Each such write must be listed
in `auth.brand_acts` under one act, so a route added tomorrow is closed to
every member until a decision opens it; and every listed route must really
go through the check, so the list cannot outlive the code.

Then the same real world the stranger test builds, walked as a member of the
brand in each role: every write their role does not hold is refused with
`brand_role_not_allowed`, every read the owner can make they can make too,
and a member of another brand is refused everything, like any stranger.
"""

import inspect
import typing
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import _leaf_routes
from app.core.rate_limit import limiter
from app.main import app
from app.modules.auth.brand_acts import ACT_ROUTES, ACTS, ROLE_ACTS, act_for, may
from app.modules.auth.brand_dependencies import (
    find_brand_access,
    find_brand_access_of_any,
)
from app.modules.auth.dependencies import CurrentBrand
from app.modules.auth.models.brand_team import BRAND_ROLES, BrandMember
from app.modules.campaigns.dependencies import get_acting_brand, get_visible_application
from tests.deal_flow import User, brand_user
from tests.modules import test_stranger_routes as stranger_walk
from tests.modules.test_stranger_routes import BODIES, QUERY, fill

Route = tuple[str, str]

# Dependencies that reach a brand through the one check.
BRAND_CHECKS = {
    find_brand_access,
    find_brand_access_of_any,
    get_acting_brand,
    get_visible_application,
}
# Route bodies that reach a deal's brand through the one check
# (`deal_memo.dependencies.party_memo`, and disputes' wrapper of it).
BRAND_CALLS = ("party_memo(", "_memo_and_payment(")
# Brand-account routes that act for no brand, each with why.
PERSONAL: dict[Route, str] = {
    ("POST", "/api/v1/brands/me"): "making a brand of your own: it is no one else's yet",
}
# Brand write routes that stay the owner's alone, each with why. None: the
# hand-over is listed under the `ownership` act, which only the owner holds,
# and deleting the account is the account's own (`me`), never the brand's.
OWNER_ALONE: dict[Route, str] = {}
MEMBER_ROLES = tuple(role for role in BRAND_ROLES if role != "owner")
# Reads whose answer is the reader's own as well as the brand's.
OWN_PARTS = {
    ("GET", "/api/v1/me/attention"),  # their own sign-ins
    ("GET", "/api/v1/brands/me/team"),  # `your_role`
}

_brand_account = typing.get_args(CurrentBrand)[1].dependency
# The stranger test's real world, fixture and all: the same objects, owned by
# brand A, walked here as its members.
world = stranger_walk.world


def every_route() -> list[APIRoute]:
    return sorted(
        (r for r in _leaf_routes(app.routes) if isinstance(r, APIRoute)),
        key=lambda r: (r.path, sorted(r.methods)[0]),
    )


def method(route: APIRoute) -> str:
    return sorted(route.methods - {"HEAD"})[0]


def calls(dependant: Any) -> Iterator[Callable[..., Any]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from calls(sub)


def checks_brand(route: APIRoute) -> bool:
    if BRAND_CHECKS & set(calls(route.dependant)):
        return True
    source = inspect.getsource(route.endpoint)
    return any(call in source for call in BRAND_CALLS)


def brand_routes() -> list[APIRoute]:
    return [r for r in every_route() if checks_brand(r)]


def listed() -> set[Route]:
    return set().union(*ACT_ROUTES.values())


# --- the list itself ------------------------------------------------------------------


def test_the_walk_finds_both_kinds_of_brand_route():
    """A guard: an empty walk would prove nothing."""
    found = {(method(r), r.path) for r in brand_routes()}

    assert ("POST", "/api/v1/campaigns") in found  # by the Brand-Id header
    assert ("POST", "/api/v1/deal-memos/{memo_id}/notes") in found  # by the deal
    assert ("POST", "/api/v1/deal-memos/{memo_id}/payment/dispute") in found
    assert ("POST", "/api/v1/applications/{application_id}/offers") in found
    assert len(found) >= 70


def test_every_listed_route_exists_and_goes_through_the_brand_check():
    gated = {(method(r), r.path) for r in brand_routes()}

    assert listed() - gated == set()


def test_every_brand_write_route_is_listed_or_the_owner_s_alone():
    writes = {(method(r), r.path) for r in brand_routes() if method(r) != "GET"}

    assert writes - listed() - OWNER_ALONE.keys() == set()


def test_every_brand_account_route_acts_for_a_brand_or_is_personal():
    """A route that signs a brand in but skips the check would ignore the team."""
    skipped = {
        (method(r), r.path)
        for r in every_route()
        if _brand_account in set(calls(r.dependant)) and not checks_brand(r)
    }

    assert skipped == PERSONAL.keys()


def test_every_act_names_routes():
    assert set(ACT_ROUTES) == set(ACTS)
    assert all(ACT_ROUTES[act] for act in ACTS)


# --- every role against every route -----------------------------------------------------


@pytest.mark.parametrize("role", BRAND_ROLES)
@pytest.mark.parametrize("route", sorted(listed()), ids=lambda r: f"{r[0]} {r[1]}")
def test_a_role_may_exactly_the_acts_it_holds(role, route):
    assert may(role, *route) is (act_for(*route) in ROLE_ACTS[role])


@pytest.mark.parametrize("role", MEMBER_ROLES)
def test_an_unlisted_write_is_refused_to_every_member_but_never_the_owner(role):
    tomorrow = ("POST", "/api/v1/campaigns/{campaign_id}/a-route-added-tomorrow")

    assert may(role, *tomorrow) is False
    assert may("owner", *tomorrow) is True


@pytest.mark.parametrize("role", BRAND_ROLES)
def test_every_role_reads_everything_of_its_brand(role):
    assert all(may(role, "GET", r.path) for r in brand_routes() if method(r) == "GET")


def test_the_roles_are_as_decided():
    """D-148's table (docs/decided/PROPOSAL_TEAM_SEATS.md 4.4), word for word."""
    decided = {
        "owner": set(ACTS),
        "admin": set(ACTS) - {"ownership"},
        "campaigns": {"campaigns", "deals", "proof"},
        "finance": {"payments"},
    }

    assert decided == ROLE_ACTS


# --- the real world, walked as each member -------------------------------------------


def member_of(db: Session, clock, brand_id: str, role: str) -> User:
    """A brand account with no brand of its own, joined to `brand_id` in `role`."""
    user = brand_user(db, clock)
    # brand_user makes a brand; this person must have none of their own.
    db.execute(
        text("DELETE FROM brand WHERE account_id = :a"),
        {"a": user.account_id},
    )
    db.add(
        BrandMember(
            brand_id=uuid.UUID(brand_id),
            account_id=user.account_id,
            role=role,
            first_name="Ravi",
            created_at=clock.now,
            updated_at=clock.now,
        )
    )
    db.flush()
    return user


def body_or_none(route: APIRoute) -> dict[str, Any] | None:
    """A valid body where the stranger test has one: a refusal is never a 422."""
    if route.body_field is None:
        return None
    return BODIES.get(route.body_field.field_info.annotation.__name__, {})


def ask(client, route: APIRoute, ids: dict[str, str], user: User):
    path = fill(route, ids)
    body = body_or_none(route)
    if body is not None:
        body = {
            k: ids["creator_id"] if v == "{creator_id}" else v for k, v in body.items()
        }
    return client.request(
        method(route), path, json=body, params=QUERY.get(route.path), headers=user.headers
    )


@pytest.mark.parametrize("role", MEMBER_ROLES)
def test_a_member_is_refused_every_write_their_role_does_not_hold(
    client, db, clock, world, role
):
    member = member_of(db, clock, world["ids"]["brand_id"], role)
    held = ROLE_ACTS[role]
    limiter.enabled = False
    try:
        wrong = []
        for route in brand_routes():
            key = (method(route), route.path)
            if key[0] == "GET" or act_for(*key) in held:
                continue
            answer = ask(client, route, world["ids"], member)
            code = answer.json().get("code") if answer.content else None
            if (answer.status_code, code) != (403, "brand_role_not_allowed"):
                wrong.append(f"{key[0]} {key[1]}: {answer.status_code} {code}")
    finally:
        limiter.enabled = True

    assert wrong == []


def test_the_least_member_reads_whatever_the_owner_reads(client, db, clock, world):
    """Finance holds the fewest acts; reads are everyone's in the brand."""
    member = member_of(db, clock, world["ids"]["brand_id"], "finance")
    owner = world["brand"]
    differ = []
    for route in brand_routes():
        key = (method(route), route.path)
        if key[0] != "GET":
            continue
        theirs = ask(client, route, world["ids"], owner)
        mine = ask(client, route, world["ids"], member)
        # The same answer, where it is a success: an error names its request.
        same_answer = (
            theirs.status_code != 200
            or key in OWN_PARTS
            or route.path.endswith((".ics", "/files"))  # links signed per request
            or mine.content == theirs.content
        )
        if mine.status_code != theirs.status_code or not same_answer:
            differ.append(
                f"{key[1]}: owner {theirs.status_code}, member {mine.status_code}"
            )

    assert differ == []


def test_a_member_of_another_brand_reaches_none_of_this_one(client, db, clock, world):
    """The stranger test, extended to members of other brands (D-148 STRIDE)."""
    elsewhere = brand_user(db, clock)
    other_brand = db.execute(
        text("SELECT id FROM brand WHERE account_id = :a"),
        {"a": elsewhere.account_id},
    ).scalar_one()
    stranger = member_of(db, clock, str(other_brand), "admin")
    limiter.enabled = False
    try:
        leaks = []
        for route in brand_routes():
            if "{" not in route.path:
                continue  # their own brand's lists: nothing of this brand's to reach
            answer = ask(client, route, world["ids"], stranger)
            if answer.status_code not in (403, 404):
                leaks.append(f"{method(route)} {route.path}: {answer.status_code}")
    finally:
        limiter.enabled = True

    assert leaks == []
