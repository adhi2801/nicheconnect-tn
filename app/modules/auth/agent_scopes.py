"""Which routes an assistant's token may reach, by scope (item 11, D-138).

Denied by default: a route is reachable with a token only when it is listed
here, under a scope the token holds. A route added to the API later is
closed to every token until a decision lists it. Each entry is a method and
the route's path template, read from the route that matched, so no id in
the path can make one route pass for another.

Never listed, whatever the scope: money (payments, UPI IDs, offers on a
fee), identity and the account's own control (phone, passkeys, sessions,
step-up codes, exports, deletion, devices, blocks, notification settings),
anything an admin does, and accepting or agreeing to anything that binds
the person (an application accepted, a memo accepted or sent). Those stay
with the person. `tests/modules/auth/test_agent_scopes.py` proves each
entry is a real route and none is one of these.
"""

from typing import Final

Route = tuple[str, str]

# Any token may ask whose it is.
ANY_SCOPE: Final[frozenset[Route]] = frozenset({("GET", "/api/v1/auth/me")})

SCOPE_ROUTES: Final[dict[str, frozenset[Route]]] = {
    # The person's deals, as they see them: never the payee's UPI ID, the
    # payment, a dispute, a shipping address or the proof's files.
    "deals:read": frozenset(
        {
            ("GET", "/api/v1/deal-memos/mine"),
            ("GET", "/api/v1/deal-memos/{memo_id}"),
            ("GET", "/api/v1/deal-memos/{memo_id}/notes"),
            ("GET", "/api/v1/deal-memos/{memo_id}/proof"),
            ("GET", "/api/v1/deal-memos/{memo_id}/record"),
            ("GET", "/api/v1/deal-memos/{memo_id}/feedback"),
            ("GET", "/api/v1/deal-memos/{memo_id}/calendar.ics"),
        }
    ),
    # Campaigns and applications, as the person sees them: a brand's own,
    # and for a creator, the open ones and their own applications.
    "campaigns:read": frozenset(
        {
            ("GET", "/api/v1/campaigns"),
            ("GET", "/api/v1/campaigns/discover"),
            ("GET", "/api/v1/campaigns/discover/for-me"),
            ("GET", "/api/v1/campaigns/{campaign_id}"),
            ("GET", "/api/v1/campaigns/{campaign_id}/summary"),
            ("GET", "/api/v1/campaigns/{campaign_id}/applications"),
            ("GET", "/api/v1/campaigns/{campaign_id}/matches"),
            ("GET", "/api/v1/campaigns/{campaign_id}/report"),
            ("GET", "/api/v1/campaigns/{campaign_id}/report.csv"),
            ("GET", "/api/v1/applications/me"),
            ("GET", "/api/v1/applications/{application_id}"),
        }
    ),
    # Applying and withdrawing (a creator), answering an invitation, and a
    # brand's shortlisting or turning down. Accepting one is the brand's own.
    "applications:write": frozenset(
        {
            ("POST", "/api/v1/campaigns/{campaign_id}/applications"),
            ("POST", "/api/v1/applications/{application_id}/withdraw"),
            ("POST", "/api/v1/applications/{application_id}/accept-invitation"),
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
