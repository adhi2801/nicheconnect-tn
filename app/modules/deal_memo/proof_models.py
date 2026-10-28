import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

# The creator's evidence that the work was done (D-024).
#
# Evidence is a public link, files, or both (D-065). A link is the only way to
# prove a post stayed up; files (screenshots, photos) are what survives the post
# being deleted, and what shows reach and insights, which have no link. Video
# stays a link for the pilot.
#
#     submitted ──approve──> approved        (by the brand, or by time: D-025)
#         └──request revision──> revision_requested ──(new submission)

PROOF_STATUSES: tuple[str, ...] = ("submitted", "approved", "revision_requested")
# Formats decide what evidence is needed once attachments exist.
PROOF_FORMATS: tuple[str, ...] = ("post", "reel", "story", "video", "other")
URL_MAX_LENGTH = 500
NOTE_MAX_LENGTH = 1000

# Proof files (D-065). Images only in the pilot; the apps convert HEIC to JPEG.
PROOF_FILE_TYPES: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
MAX_PROOF_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_PROOF = 10
#
#     pending ──(proof submitted)──> attached ──(cleaned)──> cleaned
#        └───────────────────────────────┴──(refused)──> rejected
#
# `pending` is an upload asked for; `attached` belongs to a proof, and is the
# cleaning job's queue; `cleaned` has had every piece of metadata removed and
# is the only state a brand can see.
PROOF_FILE_STATUSES: tuple[str, ...] = ("pending", "attached", "cleaned", "rejected")
PROOF_FILE_REJECTIONS: tuple[str, ...] = (
    # The stored bytes are not the ones declared (S3 should already refuse it).
    "fingerprint_mismatch",
    # Not an image, or not the image type declared.
    "not_an_image",
    # Larger than any real screenshot or photo: a decompression bomb guard.
    "too_many_pixels",
    # The object was gone when the cleaner came for it.
    "missing",
)
SHA256_HEX_PATTERN = "^[0-9a-f]{64}$"


class DeliverableProof(Base):
    __tablename__ = "deliverable_proof"
    __table_args__ = (
        CheckConstraint(f"status IN {tuple(PROOF_STATUSES)}", name="status_allowed"),
        CheckConstraint(f"format IN {tuple(PROOF_FORMATS)}", name="format_allowed"),
        # A public link, and nothing that is not one.
        CheckConstraint(
            f"content_url ~ '^https://' AND char_length(content_url) <= {URL_MAX_LENGTH}",
            name="content_url_https",
        ),
        CheckConstraint(
            f"note IS NULL OR char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"
        ),
        CheckConstraint(
            f"revision_note IS NULL OR char_length(revision_note) <= {NOTE_MAX_LENGTH}",
            name="revision_note_length",
        ),
        # Approval always has a time, and only an approval has one.
        CheckConstraint(
            "(status = 'approved') = (approved_at IS NOT NULL)",
            name="approved_at_matches_status",
        ),
        # Automatic approval is a kind of approval, never anything else.
        CheckConstraint(
            "NOT auto_approved OR status = 'approved'", name="auto_approved_is_approved"
        ),
        # One submission awaiting review per memo: a creator fixes and resubmits,
        # they do not queue up parallel attempts.
        Index(
            "uq_deliverable_proof_open",
            "deal_memo_id",
            unique=True,
            postgresql_where=text("status = 'submitted'"),
        ),
        Index("ix_deliverable_proof_memo_created_at", "deal_memo_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # RESTRICT: proof is the record of work done, so the memo stays with it.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Optional since D-065: a proof may be files alone. The service refuses a
    # proof with neither a link nor a file.
    content_url: Mapped[str | None] = mapped_column(String(URL_MAX_LENGTH), nullable=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The creator's own statement that the ad disclosure is on the post.
    # Whether the wording is compliant is an ASCI question (validation pack).
    disclosure_confirmed: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'submitted'")
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # True when the approval window ran out rather than the brand approving.
    auto_approved: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    revision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The files filed with this proof (D-065), in the order the creator
    # chose, the same order the deal record seals (D-067). "selectin":
    # a list of proofs loads every proof's files in one more query, never
    # one query per proof.
    files: Mapped[list[ProofFile]] = relationship(
        "ProofFile",
        order_by="ProofFile.position",
        lazy="selectin",
        viewonly=True,
    )
    # Set when a link check finds the post gone (D-024, D-030).
    content_removed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProofFile(Base):
    """One screenshot or photo a creator attached to a proof (D-065).

    The bytes live in S3 under `storage_key`; this row is what we know about
    them. `sha256` is what the creator declared and S3 enforced on upload;
    `clean_sha256` is the copy with its metadata removed, the only one a
    brand ever sees.
    """

    __tablename__ = "proof_file"
    __table_args__ = (
        CheckConstraint(f"status IN {PROOF_FILE_STATUSES}", name="status_allowed"),
        CheckConstraint(
            f"content_type IN {PROOF_FILE_TYPES}", name="content_type_allowed"
        ),
        CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_PROOF_FILE_BYTES}", name="size_in_range"
        ),
        CheckConstraint(f"sha256 ~ '{SHA256_HEX_PATTERN}'", name="sha256_hex"),
        CheckConstraint(
            f"clean_sha256 IS NULL OR clean_sha256 ~ '{SHA256_HEX_PATTERN}'",
            name="clean_sha256_hex",
        ),
        CheckConstraint(
            f"rejection_reason IS NULL OR rejection_reason IN {PROOF_FILE_REJECTIONS}",
            name="rejection_reason_allowed",
        ),
        # A pending upload belongs to no proof yet; an attached or cleaned one
        # always does, and says when it joined.
        CheckConstraint(
            "status <> 'pending' OR (proof_id IS NULL AND attached_at IS NULL)",
            name="pending_is_unattached",
        ),
        CheckConstraint(
            "status NOT IN ('attached', 'cleaned') "
            "OR (proof_id IS NOT NULL AND attached_at IS NOT NULL)",
            name="attached_has_proof",
        ),
        # Cleaned exactly when the clean copy is recorded.
        CheckConstraint(
            "(status = 'cleaned') = (clean_key IS NOT NULL AND clean_sha256 IS NOT NULL "
            "AND clean_size_bytes IS NOT NULL AND cleaned_at IS NOT NULL)",
            name="cleaned_has_copy",
        ),
        # A place in the proof exactly once the file has joined one (D-067):
        # 0 is shown first. A rejected file keeps its place, as it keeps its
        # proof.
        CheckConstraint(
            "(status = 'pending') = (position IS NULL)",
            name="position_once_attached",
        ),
        CheckConstraint(
            f"position IS NULL OR position BETWEEN 0 AND {MAX_FILES_PER_PROOF - 1}",
            name="position_in_range",
        ),
        # Two files never share a place. Pending rows have neither a proof
        # nor a place, and NULLs never collide.
        UniqueConstraint("proof_id", "position"),
        # Rejected exactly when there is a reason.
        CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="rejected_has_reason",
        ),
        Index("ix_proof_file_deal_memo_id", "deal_memo_id"),
        Index("ix_proof_file_proof_id", "proof_id"),
        Index("ix_proof_file_uploader_account_id", "uploader_account_id"),
        # The cleaning job's queue: attached files, oldest first.
        Index(
            "ix_proof_file_attached_queue",
            "attached_at",
            postgresql_where=text("status = 'attached'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # RESTRICT, like the proof itself: evidence stays with the deal.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # RESTRICT: a submitted proof keeps its files.
    proof_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deliverable_proof.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # RESTRICT: who uploaded evidence is part of the evidence. Account
    # deletion (E8) will decide what happens to it, with the validation pack.
    uploader_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    clean_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    clean_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clean_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Where the creator put it in the proof, from 0 (D-067). Empty while
    # pending: an upload has no place until a proof takes it.
    position: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    attached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cleaned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
