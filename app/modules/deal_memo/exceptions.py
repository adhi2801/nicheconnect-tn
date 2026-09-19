"""Domain errors for the deal memo module."""

from http import HTTPStatus

from app.core.errors import DomainError


class MemoNotFound(DomainError):
    # Also used for someone else's memo: 404, never 403, so its existence is
    # not confirmed (security.md section 2).
    status_code = HTTPStatus.NOT_FOUND
    code = "memo_not_found"
    title = "That deal memo does not exist"


class ApplicationNotAccepted(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "application_not_accepted"
    title = "Accept the application before writing a deal memo"


class MemoAlreadyExists(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "memo_already_exists"
    title = "This application already has a deal memo"


class MemoStatusConflict(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "memo_status_conflict"
    title = "This memo is not in a state where that is allowed"


class MemoNotEditable(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "memo_not_editable"
    title = "A memo can only be changed while it is a draft or a change was requested"


class BarterMemoHasNoFee(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "barter_memo_has_no_fee"
    title = "A barter campaign pays in goods, so its memo has no fee"


class PaidMemoNeedsFee(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "paid_memo_needs_fee"
    title = "This campaign type needs a fee in the memo"


class ProofNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "proof_not_found"
    title = "That proof submission does not exist"


class ProofAlreadyDecided(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "proof_already_decided"
    title = "This proof has already been reviewed"


class ProofNotSubmitted(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "proof_not_submitted"
    title = "There is no proof waiting for review"
