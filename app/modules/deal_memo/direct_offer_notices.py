"""The words a direct offer needs from the validation pack (D-189, constraint 6).

A brand who has never met us gives a name, an email and a number's code at
the link; the law asks that they are told, before they do, what we do with
those details (DPDP Rule 3; legal.md section 3.1). The link page's notice,
and the message that carries the code, are therefore the lawyer's words,
never ours. Until the validation pack gives them, each is a marked
placeholder, and `wording_ready()` keeps the whole feature off whatever
`DIRECT_OFFERS_ENABLED` says, so no placeholder can ever be served
(`tests/modules/deal_memo/test_direct_offer_api.py` proves it).

The code itself goes by the login template every code uses (D-058); a
message of its own, carrying CODE_MESSAGE, waits for a template registered
with MSG91 (item 62).
"""

PLACEHOLDER_MARK = "PLACEHOLDER"

# Shown on the link page before the brand accepts.
LINK_PAGE_NOTICE = (
    "PLACEHOLDER (constraint 6): the validation pack's notice for the direct "
    "offer link page goes here. Never served."
)
# Carried with the code sent to the number the creator named.
CODE_MESSAGE = (
    "PLACEHOLDER (constraint 6): the validation pack's wording for the direct "
    "offer code message goes here. Never sent."
)


def wording_ready() -> bool:
    """Whether every notice the feature serves is real wording, not a placeholder."""
    return not any(PLACEHOLDER_MARK in text for text in (LINK_PAGE_NOTICE, CODE_MESSAGE))
