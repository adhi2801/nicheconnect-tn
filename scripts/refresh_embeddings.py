"""Bring every embedding up to date with the text it was built from (D-052).

**This is what keeps matching working, and it is deliberately a script.**

Embedding cannot happen inside a request: the model takes about 23 seconds to
load and over 200 milliseconds per vector, both past the budgets in
`docs/standards/backend.md` section 6. So a profile edited at noon has a stale
vector until something runs this.

It is a script rather than a background job because **no job runner is
chosen** — DBOS is locked in D-047 and not installed. Run it on a schedule
(Task Scheduler, cron, a container job) until one exists, then this becomes
the body of that job rather than being rewritten.

It is safe to run as often as you like. `source_hash` means a row whose text
has not changed is skipped without touching the model, so a run with nothing
to do costs about as much as one query — measured at 0.01 s for 30 rows
against 18.6 s to embed them.

    python scripts/refresh_embeddings.py
    python scripts/refresh_embeddings.py --creators-only
    python scripts/refresh_embeddings.py --force        # after a model change
"""

import argparse
import pathlib
import sys
import time

# Run as `python scripts/refresh_embeddings.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.db.session import SessionLocal
from app.modules.matching import service


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed everything even if the text has not changed. For a model change.",
    )
    parser.add_argument("--creators-only", action="store_true", help="Skip campaigns")
    parser.add_argument("--campaigns-only", action="store_true", help="Skip creators")
    parser.add_argument(
        "--include-unpublished",
        action="store_true",
        help=(
            "Also embed creators who have not published their Passport. Off by "
            "default: they cannot be matched, so the vector would be derived "
            "personal data held for no purpose."
        ),
    )
    args = parser.parse_args()

    if args.creators_only and args.campaigns_only:
        print("Pick one of --creators-only and --campaigns-only.", file=sys.stderr)
        return 2

    started = time.perf_counter()
    with SessionLocal() as db:
        if not args.campaigns_only:
            result = service.refresh_creators(
                db,
                force=args.force,
                discoverable_only=not args.include_unpublished,
            )
            db.commit()
            print(f"creators : {result.embedded} embedded, {result.skipped} unchanged")

        if not args.creators_only:
            result = service.refresh_campaigns(db, force=args.force)
            db.commit()
            print(f"campaigns: {result.embedded} embedded, {result.skipped} unchanged")

    print(f"took {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
