"""Measure list endpoints against the budgets in backend.md section 6.

Budgets: p95 <= 300 ms for reads, <= 500 ms for writes, on seeded local data.
Run scripts/seed_dev_data.py first.

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

from datetime import UTC

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import SessionLocal
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns.models import Campaign

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--explain", action="store_true", help="Also print query plans")
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
    from datetime import datetime

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
    ]
    app.dependency_overrides.clear()
    limiter.reset()

    print(
        f"Rows: {counts[0]} campaigns, {counts[1]} applications, "
        f"{counts[2]} creators, {counts[3]} packages"
    )
    print(f"Runs per endpoint: {args.runs}\n")
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
