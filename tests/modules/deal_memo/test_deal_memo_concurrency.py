"""Two requests at once on one deal: never a 500, always one clear answer.

Review findings, PR #9: creating a memo and submitting proof both checked
"does one exist already?" and then wrote. Two requests together both passed
the check, the database's unique rule refused the second write, and the
error nobody caught reached the caller as a 500 instead of the conflict the
API documents.

Like the payment concurrency tests, these need separate, really-committing
connections, so they build their own rows and remove them afterwards. The
gap between each check and its write is held open on purpose, so the race
happens every run rather than by luck.
"""

import time
from datetime import UTC, datetime

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.modules.campaigns.models import Application
from app.modules.deal_memo import proof_service
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.exceptions import MemoAlreadyExists, ProofAlreadyDecided
from app.modules.deal_memo.models import DealMemo
from tests.modules.payment_status.test_payment_concurrency import (
    AT_ONCE,
    run_at_once,
    split,
)

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
LINK = "https://www.instagram.com/reel/concurrency/"


def test_two_simultaneous_memos_for_one_application_give_one_memo_and_conflicts(
    committed_application, monkeypatch
):
    original = memos._campaign_of

    def slow(*args, **kwargs):  # between the existence check and the write
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(memos, "_campaign_of", slow)

    results = run_at_once(
        lambda s: memos.create_memo(
            s,
            s.get(Application, committed_application),
            {"deliverables": "Three reels.", "fee_amount_paise": 800_000},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, MemoAlreadyExists)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)


def test_two_simultaneous_proof_submissions_give_one_proof_and_conflicts(
    committed_memo, monkeypatch
):
    original = proof_service.record.append

    def slow(*args, **kwargs):  # between the open-submission check and the commit
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(proof_service.record, "append", slow)

    results = run_at_once(
        lambda s: proof_service.submit_proof(
            s,
            s.get(DealMemo, committed_memo),
            {"content_url": LINK, "format": "reel"},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
