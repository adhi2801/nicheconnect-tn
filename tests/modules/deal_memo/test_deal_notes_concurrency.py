"""Notes written at the same moment on one deal (item 17, D-128).

Real, committed connections released together, every write held open
(`slow_writes`). Each note seals an entry onto the deal's record under the
deal's lock, so however many arrive at once, every one is kept, every one
is sealed, and the chain stays unbroken: no lost note, no forked record.
"""

import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.deal_memo import note_service, record_service
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.note_models import DealNote
from tests.modules.conftest import CONCURRENCY_NOW as NOW

AT_ONCE = 4


def run_together(works: list[Callable[[Any], Any]]) -> list[Any]:
    barrier = threading.Barrier(len(works))
    results: list[Any] = [None] * len(works)

    def worker(index: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                results[index] = works[index](session)
            except Exception as exc:  # collected and asserted by the test
                session.rollback()
                results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(works))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_notes_at_once_are_all_kept_and_sealed_in_one_chain(committed_memo, slow_writes):
    def write(n: int) -> Callable[[Any], Any]:
        def work(session):
            memo = session.get_one(DealMemo, committed_memo)
            side = "brand" if n % 2 else "creator"
            return note_service.add(
                session, memo, side, f"Note {n}, at the same moment.", NOW
            )

        return work

    results = run_together([write(n) for n in range(AT_ONCE)])

    assert all(isinstance(r, DealNote) for r in results), results
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, committed_memo)
        notes = session.scalars(
            select(DealNote).where(DealNote.deal_memo_id == memo.id)
        ).all()
        entries = record_service.entries_for(session, memo.id)
        check = record_service.verify(memo, entries)
        assert len(notes) == AT_ONCE
        assert [e.sequence for e in entries] == list(range(1, len(entries) + 1))
        assert sum(e.kind == "note_added" for e in entries) == AT_ONCE
        assert check.intact
        assert note_service.unchanged(session, memo) is True
