"""Which exact change a second check is for, checked before anything is sent (D-107, D-113).

Each change a code or a passkey can prove has a value its proof is bound to:
the UPI ID, the new number, the export's id, the passkey's id, "on" or
"off". This works the value out from the request and refuses, before a
message is sent or a passkey asked, a change that would be refused anyway.
Shared by asking for a code and by a passkey's answer, so the two can never
bind a proof to different values.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.auth import login_age, sessions
from app.modules.auth.models.account import Account
from app.modules.me import data_export_service as data_exports
from app.modules.me import passkey_service as passkey_changes
from app.modules.me import phone_change_service as phone_changes
from app.modules.me.step_up_schemas import (
    StepUpForExport,
    StepUpForPasskeyOnly,
    StepUpForPasskeyRemoval,
    StepUpForPhone,
    StepUpForSession,
    StepUpForUpiId,
    StepUpIn,
)
from app.modules.payment_status import upi_service


def value_of(
    db: Session,
    account: Account,
    change: StepUpIn,
    authenticated_at: datetime | None,
    now: datetime,
) -> str:
    """The value the proof for `change` is bound to; "" when it has none.

    Raises what each change's own early checks raise: LoginTooRecent,
    PhoneUnchanged, RoleNotAllowed, ExportNotFound and the export's state,
    PasskeyNotFound, SessionNotFound.
    """
    if isinstance(change, StepUpForUpiId):
        upi_service.ensure_may_replace_for_account(
            db, account, change.upi_id, authenticated_at, now
        )
        return change.upi_id
    if isinstance(change, StepUpForPhone):
        phone_changes.ensure_new_phone(account, change.new_phone)
        login_age.ensure_established_unless_passkey(db, account.id, authenticated_at, now)
        return change.new_phone
    if isinstance(change, StepUpForExport):
        data_exports.ensure_downloadable(db, account, change.export_id, now)
        return str(change.export_id)
    if isinstance(change, StepUpForPasskeyRemoval):
        passkey_changes.ensure_own(db, account, change.passkey_id)
        return str(change.passkey_id)
    if isinstance(change, StepUpForSession):
        sessions.ensure_live(db, account.id, change.session_id, now)
        return str(change.session_id)
    if isinstance(change, StepUpForPasskeyOnly):
        passkey_changes.ensure_may_have_passkeys(account)
        return "on" if change.enabled else "off"
    if change.action == "add_passkey":
        passkey_changes.ensure_may_have_passkeys(account)
    return ""
