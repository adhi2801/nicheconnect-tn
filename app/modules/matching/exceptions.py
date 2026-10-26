"""Domain errors for the matching module (mapped to Problem Details by app/core/errors.py)."""

from http import HTTPStatus

from app.core.errors import DomainError


class CreatorListNotFound(DomainError):
    # Also another brand's list: 404, never 403 (security.md section 2).
    status_code = HTTPStatus.NOT_FOUND
    code = "creator_list_not_found"
    title = "That list is not one of yours"


class ListedCreatorNotFound(DomainError):
    # Not a creator this brand could find in search today (D-129): never
    # confirms that an unpublished, withheld or blocked creator exists.
    status_code = HTTPStatus.NOT_FOUND
    code = "creator_not_found"
    title = "That creator does not exist"


class CreatorListsFull(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "creator_lists_full"
    title = "You have as many lists as you can keep; remove one first"


class CreatorListFull(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "creator_list_full"
    title = "This list holds as many creators as it can"


class CreatorListNameTaken(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "creator_list_name_taken"
    title = "You already have a list by that name"
