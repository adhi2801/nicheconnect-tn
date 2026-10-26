"""Which routes an assistant's token may reach, by scope (item 11, D-138).

Denied by default: a route is reachable with a token only when it is listed
here, under a scope the token holds. A route added to the API later is
closed to every token until a decision lists it. Each entry is a method and
the route's path template, read from the route that matched, so no id in
the path can make one route pass for another.

A token reads a deal's and a campaign's terms (fees, budgets, dates) and
where a deal stands (its stage, whether a dispute is open), as its person
sees them. Never listed, whatever the scope: a payment's details and a
dispute's content (the deal record, the campaign report, payments, pay
details, UPI IDs), counter-offers on a fee, the person's identity and the account's own
control (their phone number, passkeys, sessions, step-up codes, exports,
deletion, devices, blocks, notification settings), anything an admin does,
and accepting or agreeing to anything that binds the person (an application
or invitation accepted, a memo accepted or sent). Those stay with the
person. `tests/modules/auth/test_agent_scopes.py` proves each entry is a
real route, none is one of these by its path, and none answers a field that
is one of these.
"""

from typing import Final

Route = tuple[str, str]

# Routes any token reaches. None: `GET /auth/me` answers the person's phone
# number, which no assistant is given (D-138).
ANY_SCOPE: Final[frozenset[Route]] = frozenset()

SCOPE_ROUTES: Final[dict[str, frozenset[Route]]] = {
    # The person's deals and their terms, as they see them: never the deal
    # record (it holds payment and dispute entries), the payee's UPI ID, the
    # payment, a dispute, a shipping address or the proof's files.
    "deals:read": frozenset(
        {
            ("GET", "/api/v1/deal-memos/mine"),
            ("GET", "/api/v1/deal-memos/{memo_id}"),
            ("GET", "/api/v1/deal-memos/{memo_id}/notes"),
            ("GET", "/api/v1/deal-memos/{memo_id}/proof"),
            ("GET", "/api/v1/deal-memos/{memo_id}/feedback"),
            ("GET", "/api/v1/deal-memos/{memo_id}/calendar.ics"),
        }
    ),
    # Campaigns and applications, as the person sees them: a brand's own,
    # and for a creator, the open ones and their own applications. Never the
    # campaign report, which holds each deal's payment state.
    "campaigns:read": frozenset(
        {
            ("GET", "/api/v1/campaigns"),
            ("GET", "/api/v1/campaigns/discover"),
            ("GET", "/api/v1/campaigns/discover/for-me"),
            ("GET", "/api/v1/campaigns/{campaign_id}"),
            ("GET", "/api/v1/campaigns/{campaign_id}/summary"),
            ("GET", "/api/v1/campaigns/{campaign_id}/applications"),
            ("GET", "/api/v1/campaigns/{campaign_id}/matches"),
            ("GET", "/api/v1/applications/me"),
            ("GET", "/api/v1/applications/{application_id}"),
        }
    ),
    # Applying and withdrawing (a creator), declining an invitation, and a
    # brand's shortlisting or turning down. Accepting an application or an
    # invitation binds the person, so it is theirs alone.
    "applications:write": frozenset(
        {
            ("POST", "/api/v1/campaigns/{campaign_id}/applications"),
            ("POST", "/api/v1/applications/{application_id}/withdraw"),
            ("POST", "/api/v1/applications/{application_id}/decline-invitation"),
            ("POST", "/api/v1/applications/{application_id}/shortlist"),
            ("POST", "/api/v1/applications/{application_id}/reject"),
        }
    ),
    # A note on a deal, sealed onto its record and flagged as any is.
    "notes:write": frozenset({("POST", "/api/v1/deal-memos/{memo_id}/notes")}),
    # A creator's saved campaign alerts: listing, adding, removing.
    "alerts:write": frozenset(
        {
            ("GET", "/api/v1/me/campaign-alerts"),
            ("POST", "/api/v1/me/campaign-alerts"),
            ("DELETE", "/api/v1/me/campaign-alerts/{alert_id}"),
        }
    ),
}


def allows(scopes: list[str], method: str, path: str) -> bool:
    """Whether a token holding `scopes` may call this route (its path template)."""
    route = (method, path)
    if route in ANY_SCOPE:
        return True
    return any(route in SCOPE_ROUTES.get(scope, frozenset()) for scope in scopes)
