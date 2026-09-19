"""Domain errors for the notifications module."""

from http import HTTPStatus

from app.core.errors import DomainError


class NotificationNotFound(DomainError):
    # Also used for someone else's notification: 404, never 403, so its
    # existence is not confirmed (security.md section 2).
    status_code = HTTPStatus.NOT_FOUND
    code = "notification_not_found"
    title = "That notification does not exist"
