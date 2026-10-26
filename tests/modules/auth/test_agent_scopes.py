"""Every route of the API, against what an assistant's token may reach (item 11, D-138).

Denied by default, proven mechanically, as the stranger test proves every
object route: each route that signs a person in refuses a token unless
`agent_scopes` lists it under one of the token's scopes, so a route added
tomorrow is closed to tokens until a decision opens it. And no entry may
ever be money, identity, the account's control or an admin's.
"""

import re
import typing
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core.errors import _leaf_routes
from app.main import app
from app.modules.auth import agent_tokens
from app.modules.auth.agent_scopes import ANY_SCOPE, SCOPE_ROUTES, allows
from app.modules.auth.dependencies import get_admin, get_current_account
from app.modules.auth.models.account import Account
from app.modules.auth.models.agent_token import AGENT_SCOPES
from tests.deal_flow import creator_user

SIGNED_IN = {get_current_account, get_admin}
# Words no listed route may hold, each with what it guards.
NEVER = (
    "/admin",  # everything an admin does
    "/upi",  # where a creator is paid
    "/payment",  # payments, marking one paid, the pay details, disputes
    "/offers",  # figures on a fee
    "/phone-change",  # the account's number
    "/passkey",  # how the account signs in
    "/sessions",  # where it is signed in
    "/step-up",  # proving a risky change
    "/exports",  # a copy of the person's data
    "/deletion",  # deleting the account
    "/devices",  # where push goes
    "/blocks",  # who the person has blocked
    "/notification-preferences",  # what the person is told
    "/agent-tokens",  # tokens themselves
    "/shipment",  # a delivery address
    "/connections",  # the person's Instagram and YouTube
    "/auth/logout",
    "/auth/refresh",
    "/auth/otp",
)
# Agreeing to something that binds the person: never for an assistant. Read
# as the start of the path's last part, so `accept-invitation` is caught too
# (missed by an `endswith` check; found by the independent review).
BINDING = ("accept", "send", "publish", "mark-paid", "confirm")
# Fields no listed route may answer: payment records, disputes' progress, UPI
# IDs and the person's phone number (D-138). A deal's terms (its fee, its
# budget, `has_open_dispute`) are part of the deal and may be read.
NEVER_ANSWERED = re.compile(
    r"upi|phone|payment_state|marked_paid|payment_confirmed|confirmed_paise"
    r"|payments_sent|pay_details|^record$|reference",
    re.IGNORECASE,
)
# Listed routes with no response model, read by hand: a calendar file of the
# deal's dates, and a removal that answers nothing.
UNTYPED = {
    ("GET", "/api/v1/deal-memos/{memo_id}/calendar.ics"),
    ("DELETE", "/api/v1/me/campaign-alerts/{alert_id}"),
}


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


def signs_in(route: APIRoute) -> bool:
    return any(call in SIGNED_IN for call in calls(route.dependant))


def listed() -> set[tuple[str, str]]:
    return set(ANY_SCOPE).union(*SCOPE_ROUTES.values())


def fill(route: APIRoute) -> str:
    path = route.path
    for name in route.param_convertors:
        path = path.replace("{" + name + "}", str(uuid.uuid4()))
    return path


@pytest.fixture
def token_with(db, clock) -> Callable[[list[str]], str]:
    account = db.get_one(Account, creator_user(db, clock).account_id)

    def make(scopes: list[str]) -> str:
        _, value = agent_tokens.add(
            db,
            account,
            "Test assistant",
            scopes,
            clock.now + timedelta(days=30),
            clock.now,
        )
        return value

    return make


# --- the list itself ------------------------------------------------------------------


def test_every_listed_route_exists():
    real = {(method(r), r.path) for r in every_route()}

    assert listed() - real == set()


def test_every_scope_has_routes_and_every_route_list_is_a_scope():
    assert set(SCOPE_ROUTES) == set(AGENT_SCOPES)
    assert all(SCOPE_ROUTES.values())


@pytest.mark.parametrize("entry", sorted(listed()))
def test_no_listed_route_is_money_identity_or_control(entry):
    _, path = entry

    assert not any(word in path for word in NEVER), entry
    assert not path.rsplit("/", 1)[-1].startswith(BINDING), entry


def fields_of(annotation: Any, seen: set[type]) -> Iterator[str]:
    """Every field name in a response model, nested models included."""
    for inner in typing.get_args(annotation):
        yield from fields_of(inner, seen)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return
        seen.add(annotation)
        for name, field in annotation.model_fields.items():
            yield name
            yield from fields_of(field.annotation, seen)


@pytest.mark.parametrize(
    "route",
    [r for r in every_route() if (method(r), r.path) in listed()],
    ids=lambda r: f"{method(r)} {r.path}",
)
def test_no_listed_route_answers_a_payment_record_or_the_phone(route):
    """A route's path cannot say what it answers; its response model can."""
    if route.response_model is None:
        assert (method(route), route.path) in UNTYPED
        return

    answered = set(fields_of(route.response_model, set()))

    assert {name for name in answered if NEVER_ANSWERED.search(name)} == set()


def test_only_reads_are_in_read_scopes():
    for scope, routes in SCOPE_ROUTES.items():
        if scope.endswith(":read"):
            assert {verb for verb, _ in routes} == {"GET"}, scope


def test_allows_reads_the_template_not_the_path():
    assert allows(["deals:read"], "GET", "/api/v1/deal-memos/{memo_id}")
    assert not allows(["deals:read"], "GET", f"/api/v1/deal-memos/{uuid.uuid4()}")
    assert not allows([], "GET", "/api/v1/deal-memos/{memo_id}")
    # No route is open to every token: /auth/me answers the phone number.
    assert not allows(list(AGENT_SCOPES), "GET", "/api/v1/auth/me")


# --- every route, called with a token --------------------------------------------------

UNLISTED = [
    r for r in every_route() if signs_in(r) and (method(r), r.path) not in listed()
]
LISTED = [r for r in every_route() if (method(r), r.path) in listed()]


@pytest.mark.parametrize("route", UNLISTED, ids=lambda r: f"{method(r)} {r.path}")
def test_a_route_not_listed_refuses_a_token_with_every_scope(client, token_with, route):
    token = token_with(list(AGENT_SCOPES))

    response = client.request(
        method(route), fill(route), headers={"Authorization": f"Bearer {token}"}
    )

    expected = (
        (404, "not_found")
        if route.path.startswith("/api/v1/admin/")
        else (403, "agent_scope_missing")
    )
    assert (response.status_code, response.json().get("code")) == expected, response.text


@pytest.mark.parametrize("route", LISTED, ids=lambda r: f"{method(r)} {r.path}")
def test_a_listed_route_lets_its_scope_through_and_no_other(client, token_with, route):
    entry = (method(route), route.path)
    # A route any token reaches is tried with one scope; a token holds at least one.
    holding = [s for s, routes in SCOPE_ROUTES.items() if entry in routes] or [
        AGENT_SCOPES[0]
    ]
    others = [s for s in AGENT_SCOPES if s not in holding]
    url = fill(route)

    allowed = client.request(
        entry[0], url, headers={"Authorization": f"Bearer {token_with(holding)}"}
    )
    assert allowed.status_code != 401, allowed.text
    if allowed.status_code >= 400:
        assert allowed.json().get("code") != "agent_scope_missing", allowed.text

    if entry in ANY_SCOPE or not others:
        return
    refused = client.request(
        entry[0], url, headers={"Authorization": f"Bearer {token_with(others)}"}
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "agent_scope_missing"
