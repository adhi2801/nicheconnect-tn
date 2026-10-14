"""Domain errors for blocking (item 59, D-099)."""

from http import HTTPStatus

from app.core.errors import DomainError


class BlockTargetNotFound(DomainError):
    # Only the other side can be blocked: a creator blocks brands, a brand
    # blocks creators (item 59).
    status_code = HTTPStatus.NOT_FOUND
    code = "block_target_not_found"
    title = "There is nobody with that id you could block"


class BlockNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "block_not_found"
    title = "That block does not exist, or it is not yours"
