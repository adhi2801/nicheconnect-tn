"""The words a direct offer needs from the validation pack (D-189, constraint 6).

A brand who has never met us gives a name, an email and a number's code at
the link; the law asks that they are told, before they do, what we do with
those details (DPDP Rule 3; legal.md section 3.1). The link page's notice,
and the message that carries the code, are therefore the lawyer's words,
never ours.

- The link page's notice is served from here. Until the validation pack
  gives it, it is a marked placeholder.
- The code's message is a WhatsApp template registered with MSG91, whose
  words are the validation pack's; the code goes out on it, never on the
  login template (D-058), which says nothing about an offer. Until it is
  registered and named in `MSG91_DIRECT_OFFER_TEMPLATE`, there is none.

`ready()` keeps the whole feature off while either is missing, whatever
`DIRECT_OFFERS_ENABLED` says, so no placeholder is ever served and no code
for an offer goes out without its notice
(`tests/modules/deal_memo/test_direct_offer_api.py` proves both).
"""

from app.core.config import settings

PLACEHOLDER_MARK = "PLACEHOLDER"

# Shown on the link page before the brand accepts.
LINK_PAGE_NOTICE = (
    "PLACEHOLDER (constraint 6): the validation pack's notice for the direct "
    "offer link page goes here. Never served."
)


def wording_ready() -> bool:
    """Whether the link page's notice is real wording, not a placeholder."""
    return PLACEHOLDER_MARK not in LINK_PAGE_NOTICE


def code_template_ready() -> bool:
    """Whether a template carrying the code's notice is named for MSG91."""
    return settings.msg91_direct_offer_template is not None


def ready() -> bool:
    """Whether both notices exist: the link page's, and the code message's."""
    return wording_ready() and code_template_ready()


def refuse_switch_without_wording(enabled: bool) -> None:
    """Stop the app starting with direct offers on while either notice is missing.

    Called at startup (app/main.py), so the switch can never say "on" to a
    client (`GET /api/v1/features`) while the feature would refuse; the
    routes check `ready()` again in any case.
    """
    if enabled and not wording_ready():
        raise RuntimeError(
            "DIRECT_OFFERS_ENABLED is on, but the link page's notice is still a "
            "placeholder: put the validation pack's wording in "
            "app/modules/deal_memo/direct_offer_notices.py first (constraint 6)"
        )
    if enabled and not code_template_ready():
        raise RuntimeError(
            "DIRECT_OFFERS_ENABLED is on, but MSG91_DIRECT_OFFER_TEMPLATE is unset: "
            "register the code message's template, with the validation pack's "
            "wording, and name it there first (constraint 6)"
        )
