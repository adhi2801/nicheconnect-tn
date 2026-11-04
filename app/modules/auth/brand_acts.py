"""What each role in a brand may do, route by route (item 13, D-148).

Denied by default, as assistants' scopes are (`auth.agent_scopes`): a brand
write route a member may reach is listed here under one act, and each role
holds a set of acts. A write route added later is closed to every member
until a decision lists it; the owner, whose brand it is, is never refused.
Reads are open to everyone in the brand: a team that cannot see the deals it
works on cannot do its job.

Each entry is a method and the route's path template, read from the route
that matched, so no id in a path can make one route pass for another.
`tests/modules/auth/test_brand_acts.py` proves every entry is a real route,
every brand write route is listed or deliberately the owner's alone, and
every role is refused every act it does not hold.
"""

from typing import Final

from app.modules.auth.models.brand_team import BRAND_ROLES

Route = tuple[str, str]

# The acts, in the words of docs/decided/PROPOSAL_TEAM_SEATS.md section 4.4.
ACTS: Final[tuple[str, ...]] = (
    "campaigns",
    "deals",
    "proof",
    "payments",
    "profile",
    "team",
    "ownership",
)

ROLE_ACTS: Final[dict[str, frozenset[str]]] = {
    "owner": frozenset(ACTS),
    "admin": frozenset({"campaigns", "deals", "proof", "payments", "profile", "team"}),
    # The person running campaigns judges the work, so approving proof is
    # theirs (D-148); money and the team are not.
    "campaigns": frozenset({"campaigns", "deals", "proof"}),
    # Money, kept apart from campaigns, as Upwork keeps its finance admin.
    "finance": frozenset({"payments"}),
}
if set(ROLE_ACTS) != set(BRAND_ROLES):
    raise RuntimeError("ROLE_ACTS must name exactly the brand roles (D-148)")

ACT_ROUTES: Final[dict[str, frozenset[Route]]] = {
    "campaigns": frozenset(
        {
            ("POST", "/api/v1/campaigns"),
            ("PATCH", "/api/v1/campaigns/{campaign_id}"),
            ("POST", "/api/v1/campaigns/{campaign_id}/publish"),
            ("POST", "/api/v1/campaigns/{campaign_id}/close"),
            ("POST", "/api/v1/campaigns/{campaign_id}/cancel"),
            ("POST", "/api/v1/campaigns/{campaign_id}/invitations"),
            ("POST", "/api/v1/applications/{application_id}/withdraw-invitation"),
            ("POST", "/api/v1/applications/{application_id}/shortlist"),
            ("POST", "/api/v1/applications/{application_id}/accept"),
            ("POST", "/api/v1/applications/{application_id}/reject"),
            ("POST", "/api/v1/applications/{application_id}/offers"),
            ("POST", "/api/v1/applications/{application_id}/offers/{offer_id}/accept"),
            ("POST", "/api/v1/applications/{application_id}/offers/{offer_id}/decline"),
            ("DELETE", "/api/v1/applications/{application_id}/offers/{offer_id}"),
            ("POST", "/api/v1/creator-lists"),
            # A brief drafted from the brand's words (item 40, D-156).
            ("POST", "/api/v1/brief-drafts"),
            ("PATCH", "/api/v1/creator-lists/{list_id}"),
            ("DELETE", "/api/v1/creator-lists/{list_id}"),
            ("PUT", "/api/v1/creator-lists/{list_id}/creators/{creator_id}"),
            ("DELETE", "/api/v1/creator-lists/{list_id}/creators/{creator_id}"),
            # A block is the brand's (D-148 piece 2): it stops the whole brand
            # reaching a creator, so it is for those who reach creators.
            ("POST", "/api/v1/me/blocks"),
            ("DELETE", "/api/v1/me/blocks/{block_id}"),
        }
    ),
    "deals": frozenset(
        {
            ("POST", "/api/v1/deal-memos/for-application/{application_id}"),
            ("PATCH", "/api/v1/deal-memos/{memo_id}"),
            ("POST", "/api/v1/deal-memos/{memo_id}/send"),
            ("POST", "/api/v1/deal-memos/{memo_id}/cancel"),
            ("POST", "/api/v1/deal-memos/{memo_id}/repeat"),
            ("POST", "/api/v1/deal-memos/{memo_id}/notes"),
            ("PUT", "/api/v1/deal-memos/{memo_id}/shipment"),
            ("POST", "/api/v1/deal-memos/{memo_id}/feedback"),
        }
    ),
    # Judging the work: proof, which starts the payment clock, and drafts.
    "proof": frozenset(
        {
            ("POST", "/api/v1/deal-memos/{memo_id}/proof/{proof_id}/approve"),
            ("POST", "/api/v1/deal-memos/{memo_id}/proof/{proof_id}/request-revision"),
            ("POST", "/api/v1/deal-memos/{memo_id}/drafts/{draft_id}/approve"),
            ("POST", "/api/v1/deal-memos/{memo_id}/drafts/{draft_id}/request-changes"),
        }
    ),
    "payments": frozenset(
        {
            ("POST", "/api/v1/deal-memos/{memo_id}/payment/mark-paid"),
            ("POST", "/api/v1/brands/me/payments/mark-paid"),
            ("POST", "/api/v1/deal-memos/{memo_id}/payment/dispute"),
            ("POST", "/api/v1/deal-memos/{memo_id}/payment/dispute/entries"),
            ("POST", "/api/v1/deal-memos/{memo_id}/payment/dispute/close"),
        }
    ),
    "profile": frozenset(
        {
            ("PATCH", "/api/v1/brands/me"),
            ("POST", "/api/v1/brands/me/domain"),
            ("POST", "/api/v1/brands/me/domain/check"),
            ("DELETE", "/api/v1/brands/me/domain"),
        }
    ),
    "team": frozenset(
        {
            ("POST", "/api/v1/brands/me/team/invites"),
            ("DELETE", "/api/v1/brands/me/team/invites/{invite_id}"),
            ("PATCH", "/api/v1/brands/me/team/members/{member_id}"),
            ("DELETE", "/api/v1/brands/me/team/members/{member_id}"),
        }
    ),
    "ownership": frozenset({("POST", "/api/v1/brands/me/team/ownership")}),
}

# Every listed route, and the act it needs.
_ACT_OF: Final[dict[Route, str]] = {
    route: act for act, routes in ACT_ROUTES.items() for route in routes
}
if len(_ACT_OF) != sum(len(routes) for routes in ACT_ROUTES.values()):
    raise RuntimeError("A brand route is listed under two acts; each needs exactly one")


# Who on a team hears what (D-148 piece 2): a notice to a brand's owner about
# one of these is copied to every live member whose role holds its act, so
# each person hears of the work they do and no more. A notice not listed
# (a session, a passkey, a deletion, the team itself) is the owner's own.
NOTICE_ACTS: Final[dict[str, str]] = {
    "application_received": "campaigns",
    "application_withdrawn": "campaigns",
    "invitation_accepted": "campaigns",
    "invitation_declined": "campaigns",
    "offer_received": "campaigns",
    "offer_accepted": "campaigns",
    "offer_declined": "campaigns",
    "offer_withdrawn": "campaigns",
    "memo_accepted": "deals",
    "memo_declined": "deals",
    "memo_change_requested": "deals",
    "memo_cancelled": "deals",
    "note_added": "deals",
    "product_received": "deals",
    "feedback_received": "deals",
    "proof_submitted": "proof",
    "draft_submitted": "proof",
    "payment_confirmed": "payments",
    "content_withheld": "profile",
    "content_restored": "profile",
}
if not set(NOTICE_ACTS.values()) <= set(ACTS):
    raise RuntimeError("A notice is copied for an act that does not exist (D-148)")

# The notices to a creator that are one person's act for the brand, so the
# creator is shown that member's first name (D-148). Denied by default: a
# notice of the deal's own rules (approved by the clock), of matching (an
# alert) or of anything a job does names nobody, even when it fires inside
# a member's request.
NAMED_TO_CREATORS: Final[frozenset[str]] = frozenset(
    {
        "application_shortlisted",
        "application_accepted",
        "application_rejected",
        "invitation_received",
        "invitation_withdrawn",
        "offer_received",
        "offer_accepted",
        "offer_declined",
        "offer_withdrawn",
        "memo_sent",
        "memo_cancelled",
        "note_added",
        "product_shipped",
        "proof_approved",
        "proof_revision_requested",
        "draft_approved",
        "draft_changes_requested",
        "payment_marked_paid",
    }
)


def roles_hearing(notification_type: str) -> frozenset[str]:
    """The member roles a brand's notice of this type is copied to; none if unlisted."""
    act = NOTICE_ACTS.get(notification_type)
    if act is None:
        return frozenset()
    return frozenset(r for r, acts in ROLE_ACTS.items() if act in acts and r != "owner")


def act_for(method: str, path: str) -> str | None:
    """The act a brand write route needs, or None when it is not listed."""
    return _ACT_OF.get((method, path))


def may(role: str, method: str, path: str) -> bool:
    """Whether someone in `role` may call this route for their brand.

    Reads are open to every role. A write must be listed under an act the
    role holds, except for the owner, whose brand it is.
    """
    if method in ("GET", "HEAD"):
        return True
    if role == "owner":
        return True
    act = act_for(method, path)
    return act is not None and act in ROLE_ACTS.get(role, frozenset())
