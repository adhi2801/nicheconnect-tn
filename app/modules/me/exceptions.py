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
