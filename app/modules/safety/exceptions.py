"""Domain errors for blocking (item 59, D-099)."""

from http import HTTPStatus

from app.core.errors import DomainError


class BlockTargetNotFound(DomainError):
    # Only the other side can be blocked: a creator blocks brands, a brand
    # blocks creators (item 59).
    status_code = HTTPStatus.NOT_FOUND
    code = "block_target_not_found"
    title = "There is nobody with that id you could block"


class ContentWithheld(DomainError):
    # 451, "Unavailable For Legal Reasons" (RFC 7725), as GitHub answers a
    # takedown (item 52). It says the item exists and why it cannot be shown:
    # it was public, so there is no secret to keep, and the truth is the
    # honest answer. The owner never gets it for their own item.
    status_code = HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS
    code = "content_withheld"
    # True for every basis: an order, or a report the IT Rules make us act on.
    title = "This is unavailable for legal reasons"


class OwnContentWithheld(DomainError):
    # The owner's side of a takedown (item 52): their own profile, brand or
    # campaign is withheld, so it may not reach anyone new (an application,
    # an invitation, accepting one) until it is lifted. Deals already agreed
    # carry on. Never 451: they can see their own item, and need to know why
    # they cannot use it.
    status_code = HTTPStatus.CONFLICT
    code = "own_content_withheld"
    title = (
        "Yours is withheld for legal reasons, so it cannot reach anyone new "
        "until that is lifted"
    )


class BlockNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "block_not_found"
    title = "That block does not exist, or it is not yours"
