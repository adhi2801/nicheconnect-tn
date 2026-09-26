"""Measure endpoints against the budgets in backend.md section 6.

Budgets: p95 <= 300 ms for reads, <= 500 ms for writes, on seeded local data.
Run scripts/seed_dev_data.py first.

Writes are measured by taking whole deals through the API, from a new
campaign to a confirmed payment, inside one transaction that is rolled back
at the end. Nothing they write is kept, which matters because the deal
record cannot be deleted once written (D-057).

    python scripts/measure_performance.py
    python scripts/measure_performance.py --runs 100 --explain
"""

import argparse
import pathlib
import statistics
import sys
import time

# Run as `python scripts/measure_performance.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import SessionLocal, engine, get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns.models import Campaign
from app.modules.payment_status.service import MAX_BULK_MARK_PAID

READ_BUDGET_MS = 300
WRITE_BUDGET_MS = 500

# Queries behind the list endpoints, checked with EXPLAIN to confirm the
# indexes are used (database.md section 5).
EXPLAINED_QUERIES = {
    "discover open campaigns, newest first": """
        SELECT * FROM campaign WHERE status = 'open'
        ORDER BY created_at DESC, id DESC LIMIT 21
    """,
    "discover filtered by niche and city": """
        SELECT * FROM campaign
        WHERE status = 'open' AND niches @> ARRAY['food']::text[]
          AND cities @> ARRAY['Madurai']::text[]
        ORDER BY created_at DESC, id DESC LIMIT 21
    """,
    "applications for one campaign": """
        SELECT * FROM application WHERE campaign_id = :campaign_id
        ORDER BY created_at DESC, id DESC LIMIT 21
    """,
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(int(len(ordered) * fraction), len(ordered) - 1)
    return ordered[index]


def measure(
    client: TestClient,
    name: str,
    method: str,
    url: str,
    headers: dict,
    runs: int,
    budget: int,
    **kwargs,
) -> dict:
    limiter.reset()  # the limits are not what we are measuring
    timings: list[float] = []
    for _ in range(runs):
        limiter.reset()
        started = time.perf_counter()
        response = client.request(method, url, headers=headers, **kwargs)
        timings.append((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise SystemExit(f"{name}: {response.status_code} {response.text[:200]}")
    return {
        "name": name,
        "p50": statistics.median(timings),
        "p95": percentile(timings, 0.95),
        "max": max(timings),
        "budget": budget,
    }


def summarise(name: str, timings: list[float], budget: int) -> dict:
    return {
        "name": name,
        "p50": statistics.median(timings),
        "p95": percentile(timings, 0.95),
        "max": max(timings),
        "budget": budget,
    }


BULK_ROUNDS = 5
# The most a brand may send in one call: the worst case is the one that matters.
BULK_ROWS = MAX_BULK_MARK_PAID


def measure_writes(
    deals: int, brand_headers: dict, creator_headers: dict, now: datetime
) -> list[dict]:
    """Every write in a deal's life, timed, then rolled back.

    Three phases, all inside one transaction that is rolled back at the end:

    1. `deals` whole deals, from a new campaign to a confirmed payment, with
       a dispute opened, added to and closed on each payment on the way.
    2. `BULK_ROUNDS` bank bulk transfers of `BULK_ROWS` deals each, through
       the bulk mark-paid.
    3. `deals` rounds of rate card writes, by a creator made for the run:
       the seeded creators may already hold the ten-package limit.
    """
    timings: dict[str, list[float]] = defaultdict(list)
    due_on = (now + timedelta(days=60)).date().isoformat()

    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def write(
        name: str | None,
        url: str,
        headers: dict,
        body: dict | None = None,
        method: str = "POST",
    ) -> dict:
        """One request; timed under `name`, or untimed setup when None."""
        limiter.reset()  # the limits are not what we are measuring
        started = time.perf_counter()
        response = client.request(method, url, json=body, headers=headers)
        if name is not None:
            timings[name].append((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise SystemExit(
                f"{name or url}: {response.status_code} {response.text[:200]}"
            )
        return response.json() if response.content else {}

    memos = "/api/v1/deal-memos"

    def approved_deal(timed: bool) -> str:
        """A deal taken to approved work, its payment now owed."""

        def name(label: str) -> str | None:
            return label if timed else None

        campaign = write(
            name("POST /campaigns"),
            "/api/v1/campaigns",
            brand_headers,
            {
                "title": "Pongal sweets launch",
                "description": "Three reels featuring our new sweet box.",
                "campaign_type": "paid",
                "budget_min_paise": 500_000,
                "budget_max_paise": 1_500_000,
                "cities": ["Madurai"],
                "niches": ["food"],
                "deliverables": "3 Instagram reels",
            },
        )["id"]
        write(
            name("POST /campaigns/{id}/publish"),
            f"/api/v1/campaigns/{campaign}/publish",
            brand_headers,
        )
        application = write(
            name("POST /campaigns/{id}/applications"),
            f"/api/v1/campaigns/{campaign}/applications",
            creator_headers,
            {"pitch": "I cover food in Madurai for local families, in Tamil."},
        )["id"]
        for action in ("shortlist", "accept"):
            write(
                name(f"POST /applications/{{id}}/{action}"),
                f"/api/v1/applications/{application}/{action}",
                brand_headers,
            )
        memo = write(
            name("POST /deal-memos/for-application/{id}"),
            f"{memos}/for-application/{application}",
            brand_headers,
            {
                "deliverables": "3 Instagram reels, 1 story set.",
                "fee_amount_paise": 800_000,
                "content_due_on": due_on,
            },
        )["id"]
        write(name("POST /deal-memos/{id}/send"), f"{memos}/{memo}/send", brand_headers)
        write(
            name("POST /deal-memos/{id}/accept"),
            f"{memos}/{memo}/accept",
            creator_headers,
        )
        proof = write(
            name("POST /deal-memos/{id}/proof"),
            f"{memos}/{memo}/proof",
            creator_headers,
            {
                "content_url": "https://www.instagram.com/reel/abc123/",
                "format": "reel",
                "disclosure_confirmed": True,
            },
        )["id"]
        write(
            name("POST /deal-memos/{id}/proof/{id}/approve"),
            f"{memos}/{memo}/proof/{proof}/approve",
            brand_headers,
        )
        return str(memo)

    try:
        # 1. Whole deals, with a dispute on each payment.
        for _ in range(deals):
            memo = approved_deal(timed=True)
            write(
                "POST /deal-memos/{id}/payment/mark-paid",
                f"{memos}/{memo}/payment/mark-paid",
                brand_headers,
                {"method": "upi", "reference": "412345678901"},
            )
            dispute = f"{memos}/{memo}/payment/dispute"
            write(
                "POST /deal-memos/{id}/payment/dispute",
                dispute,
                creator_headers,
                {"reason": "The reference does not match anything in my bank statement."},
            )
            write(
                "POST .../payment/dispute/entries",
                f"{dispute}/entries",
                brand_headers,
                {"note": "Attaching the bank's confirmation for that reference."},
            )
            write(
                "POST .../payment/dispute/close",
                f"{dispute}/close",
                creator_headers,
                {"outcome": "resolved_paid"},
            )
            write(
                "POST /deal-memos/{id}/payment/confirm",
                f"{memos}/{memo}/payment/confirm",
                creator_headers,
            )

        # 2. Bank bulk transfers: set up untimed, only the bulk call is timed.
        for _ in range(BULK_ROUNDS):
            owed = [approved_deal(timed=False) for _ in range(BULK_ROWS)]
            write(
                f"POST /brands/me/payments/mark-paid ({BULK_ROWS} rows)",
                "/api/v1/brands/me/payments/mark-paid",
                brand_headers,
                {
                    "payments": [
                        {
                            "memo_id": memo,
                            "method": "bank_transfer",
                            "reference": f"41234567{i:04d}",
                        }
                        for i, memo in enumerate(owed)
                    ]
                },
            )

        # 3. The rate card, by a creator made for this run.
        account = Account(phone="+919000099999", role="creator")
        db.add(account)
        db.flush()
        db.add(
            Creator(
                account_id=account.id,
                account_role="creator",
                display_name="Measure Creator",
                handle="measure.creator",
                city="Madurai",
                niches=["food"],
                languages=["en"],
            )
        )
        db.flush()
        token, _ = create_access_token(account.id, "creator", now)
        rate_card_headers = {"Authorization": f"Bearer {token}"}
        cards = "/api/v1/creators/me"
        for _ in range(deals):
            write(
                "PUT /creators/me/channels/{platform}",
                f"{cards}/channels/instagram",
                rate_card_headers,
                {
                    "profile_url": "https://instagram.com/measure.creator",
                    "followers": 24_000,
                    "average_views": 6_000,
                },
                method="PUT",
            )
            package = write(
                "POST /creators/me/packages",
                f"{cards}/packages",
                rate_card_headers,
                {
                    "platform": "instagram",
                    "format": "reel",
                    "title": "1 Instagram Reel",
                    "price_paise": 800_000,
                    "delivery_days": 5,
                    "position": 0,
                },
            )["id"]
            write(
                "PATCH /creators/me/packages/{id}",
                f"{cards}/packages/{package}",
                rate_card_headers,
                {"price_paise": 900_000},
                method="PATCH",
            )
            write(
                "DELETE /creators/me/packages/{id}",
                f"{cards}/packages/{package}",
                rate_card_headers,
                method="DELETE",
            )
            write(
                "POST /creators/me/rate-card/publish",
                f"{cards}/rate-card/publish",
                rate_card_headers,
            )
            write(
                "POST /creators/me/rate-card/unpublish",
                f"{cards}/rate-card/unpublish",
                rate_card_headers,
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        outer.rollback()
        connection.close()

    return [summarise(name, values, WRITE_BUDGET_MS) for name, values in timings.items()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--explain", action="store_true", help="Also print query plans")
    parser.add_argument(
        "--deals",
        type=int,
        default=30,
        help="Whole deals to take through the writes, rolled back afterwards",
    )
    args = parser.parse_args()

    if settings.environment != "local":
        print(
            f"Refusing to run outside local (ENVIRONMENT={settings.environment}).",
            file=sys.stderr,
        )
        return 1

    with SessionLocal() as db:
        # A brand that actually owns campaigns with applications.
        brand_id = db.execute(
            text(
                "SELECT c.brand_id FROM application a JOIN campaign c ON c.id = a.campaign_id "
                "GROUP BY c.brand_id ORDER BY count(*) DESC LIMIT 1"
            )
        ).scalar()
        brand = (
            db.get(Brand, brand_id)
            if brand_id
            else db.scalars(select(Brand).limit(1)).first()
        )
        creator = db.scalars(select(Creator).limit(1)).first()
        campaign = db.scalars(
            select(Campaign).where(Campaign.status == "open").limit(1)
        ).first()
        # The brand's own busiest campaign: the endpoint refuses other brands.
        busiest = db.execute(
            text(
                "SELECT a.campaign_id, count(*) AS n FROM application a "
                "JOIN campaign c ON c.id = a.campaign_id "
                "WHERE c.brand_id = :brand_id "
                "GROUP BY a.campaign_id ORDER BY n DESC LIMIT 1"
            ),
            {"brand_id": brand.id},
        ).first()
        # The largest media kit and public page: the most packages, published.
        fullest = db.execute(
            text(
                "SELECT c.id, c.handle FROM creator c "
                "LEFT JOIN creator_package p ON p.creator_id = c.id "
                "WHERE c.passport_published_at IS NOT NULL "
                "GROUP BY c.id ORDER BY count(p.id) DESC LIMIT 1"
            )
        ).first()
        counts = db.execute(
            text(
                "SELECT (SELECT count(*) FROM campaign), (SELECT count(*) FROM application),"
                " (SELECT count(*) FROM creator), (SELECT count(*) FROM creator_package)"
            )
        ).first()

    if brand is None or creator is None or campaign is None or fullest is None:
        print(
            "No sample data. Run: python scripts/seed_dev_data.py --reset",
            file=sys.stderr,
        )
        return 1

    # A fixed clock keeps tokens valid for the whole run.
    now = datetime.now(UTC)
    app.dependency_overrides[get_now] = lambda: now
    brand_token, _ = create_access_token(brand.account_id, "brand", now)
    creator_token, _ = create_access_token(creator.account_id, "creator", now)
    brand_headers = {"Authorization": f"Bearer {brand_token}"}
    creator_headers = {"Authorization": f"Bearer {creator_token}"}
    busiest_campaign_id = busiest[0] if busiest else campaign.id

    client = TestClient(app)
    results = [
        measure(
            client,
            "GET /campaigns/discover",
            "GET",
            "/api/v1/campaigns/discover",
            creator_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /campaigns/discover?city&niche",
            "GET",
            "/api/v1/campaigns/discover?city=Madurai&niche=food",
            creator_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /campaigns (mine)",
            "GET",
            "/api/v1/campaigns",
            brand_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /campaigns/{id}",
            "GET",
            f"/api/v1/campaigns/{campaign.id}",
            creator_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /campaigns/{id}/applications",
            "GET",
            f"/api/v1/campaigns/{busiest_campaign_id}/applications",
            brand_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /applications/me",
            "GET",
            "/api/v1/applications/me",
            creator_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /auth/me",
            "GET",
            "/api/v1/auth/me",
            creator_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /creators/{id}/media-kit",
            "GET",
            f"/api/v1/creators/{fullest.id}/media-kit",
            brand_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /creators/by-handle/{handle}",
            "GET",
            f"/api/v1/creators/by-handle/{fullest.handle}",
            {},
            args.runs,
            READ_BUDGET_MS,
        ),
        measure(
            client,
            "GET /rate-guidance (niche and city)",
            "GET",
            "/api/v1/rate-guidance?platform=instagram&format=reel"
            "&followers=20000&niche=food&city=Madurai",
            brand_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
    ]
    results += measure_writes(args.deals, brand_headers, creator_headers, now)
    app.dependency_overrides.clear()
    limiter.reset()

    print(
        f"Rows: {counts[0]} campaigns, {counts[1]} applications, "
        f"{counts[2]} creators, {counts[3]} packages"
    )
    print(f"Runs per read: {args.runs}; whole deals for the writes: {args.deals}\n")
    print(
        f"{'endpoint':42} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8} {'budget':>8}  verdict"
    )
    failures = 0
    for row in results:
        ok = row["p95"] <= row["budget"]
        failures += 0 if ok else 1
        print(
            f"{row['name']:42} {row['p50']:8.1f} {row['p95']:8.1f} {row['max']:8.1f} "
            f"{row['budget']:8d}  {'OK' if ok else 'OVER BUDGET'}"
        )

    if args.explain:
        print("\nQuery plans:")
        with SessionLocal() as db:
            for name, sql in EXPLAINED_QUERIES.items():
                print(f"\n--- {name}")
                params = (
                    {"campaign_id": busiest_campaign_id} if ":campaign_id" in sql else {}
                )
                plan = (
                    db.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}"), params)
                    .scalars()
                    .all()
                )
                for line in plan:
                    print("   ", line)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
