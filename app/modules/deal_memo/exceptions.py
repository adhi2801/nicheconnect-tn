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


class MemoNeedsDueDate(DomainError):
    # Without an agreed date nothing can ever be late, so a creator who never
    # delivers would never show on their delivery record (D-038 point a).
    status_code = HTTPStatus.CONFLICT
    code = "memo_needs_due_date"
    title = "Set the date the work is due before sending this memo"


class DueDateHasPassed(DomainError):
    # A date already behind us is not a date anybody can agree to: accepting
    # it would make the creator overdue on the day they said yes.
    status_code = HTTPStatus.CONFLICT
    code = "due_date_has_passed"
    title = "The agreed due date has already passed. Set a new one first"


class CheckpointNotFound(DomainError):
    # No checkpoint covers this deal yet (its first entry is newer than the
    # last one), or none exists for the date asked about.
    status_code = HTTPStatus.NOT_FOUND
    code = "checkpoint_not_found"
    title = "No daily checkpoint covers this deal for that date yet"


class RecordDoesNotMatchCheckpoint(DomainError):
    # The record, recomputed today, no longer leads to a root the authorities
    # stamped. That is what a rewrite or a backdated entry looks like, so it is
    # answered plainly rather than as a server error (D-060).
    status_code = HTTPStatus.CONFLICT
    code = "record_does_not_match_checkpoint"
    title = "The deal record no longer matches its stamped daily checkpoint"


# --- proof files (D-065) --------------------------------------------------------


class TooManyPendingUploads(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "too_many_pending_uploads"
    title = "Finish or submit the uploads already started before starting more"


class ProofFileNotFound(DomainError):
    # Someone else's file, a file on another deal, or one already used: all
    # the same answer, so nothing about other files is confirmed.
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "proof_file_not_found"
    title = "A file in this proof is not one of your uploads for this deal"


class ProofFileNotUploaded(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "proof_file_not_uploaded"
    title = "A file in this proof has not finished uploading"


class ProofNeedsEvidence(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "proof_needs_evidence"
    title = "A proof needs a link to the post, at least one file, or both"


class ProofReadingNotFound(DomainError):
    # A file not on this proof gets the same answer: nothing about other
    # deals' files is confirmed.
    status_code = HTTPStatus.NOT_FOUND
    code = "proof_reading_not_found"
    title = "That file on this proof has not been read"


class ProofReadingNotMarkable(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "proof_reading_not_markable"
    title = "Only numbers that were read from the screenshot can be marked as misread"


class ProofReadingAlreadyMarked(DomainError):
    # Once: the mark sits next to the reading for good, so the brand never
    # sees a note that changes after they read it.
    status_code = HTTPStatus.CONFLICT
    code = "proof_reading_already_marked"
    title = "This reading has already been marked as misread"
