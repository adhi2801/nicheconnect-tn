"""Domain errors for the `me` module (mapped to Problem Details by app/core/errors.py)."""

from http import HTTPStatus

from app.core.errors import DomainError


class ExportNotFound(DomainError):
    # Also someone else's export: 404, never 403 (security.md section 2).
    status_code = HTTPStatus.NOT_FOUND
    code = "export_not_found"
    title = "That export is not one of yours"


class ExportAlreadyPreparing(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "export_already_preparing"
    title = "Your data export is already being prepared"

    def __init__(self) -> None:
        super().__init__(
            "You will be told in the app when it is ready, usually in minutes."
        )


class ExportNotReady(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "export_not_ready"
    title = "That export is still being prepared"


class ExportFailed(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "export_failed"
    title = "That export could not be made; ask for a new one"


class ExportAlreadyDownloaded(DomainError):
    # Downloaded once, then destroyed (D-111): no copy is left to give.
    status_code = HTTPStatus.CONFLICT
    code = "export_already_downloaded"
    title = "That export was already downloaded; ask for a new one"


class ExportExpired(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "export_expired"
    title = "That export was not downloaded within 24 hours; ask for a new one"


class DeletionHeldByDeals(DomainError):
    # Deleting mid-deal would leave the other side without the person they
    # were working with, or let a brand leave to avoid paying (D-122, 1A).
    status_code = HTTPStatus.CONFLICT
    code = "deletion_held_by_deals"
    title = "Finish or cancel your deals before deleting your account"

    def __init__(self, unfinished: int) -> None:
        super().__init__(
            f"{unfinished} of your deals are not finished. Each needs to be "
            "finished, declined or cancelled, with no payment dispute open; "
            "GET /api/v1/me/deletion lists them."
        )


class DeletionAlreadyRequested(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "deletion_already_requested"
    title = "Your account is already waiting to be deleted"

    def __init__(self) -> None:
        super().__init__(
            "GET /api/v1/me/deletion says when; DELETE it to keep your account."
        )
