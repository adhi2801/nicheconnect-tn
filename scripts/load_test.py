"""Many people at once, against the budgets in backend.md section 6 (item 5, D-092).

`scripts/measure_performance.py` times each endpoint for one person. Launch
is many: this runs brands and creators through what they really do, all at
once, and fails if any endpoint's p95 is over budget (300 ms for a read, 500
ms for a write) or any request fails.

Each simulated person signs in as a different seeded sample account, so the
per-account rate limits behave as they would for real people. The one write
reads each creator's availability and puts the same value back: a real write
path that changes nothing. Nothing touches the deal record, which can never
be deleted (D-057).

    uv run python scripts\\seed_dev_data.py --reset --brands 40 --creators 400
    uv run uvicorn app.main:app --workers 4
    uv run --group load locust -f scripts/load_test.py --headless \\
        --host http://127.0.0.1:8000 --users 200 --spawn-rate 20 --run-time 3m

Use 127.0.0.1, not localhost: on Windows, localhost tries IPv6 first and
waits about two seconds before falling back, which every new connection then
shows as a two-second request (found on the first run, 12 October 2026).

It refuses to run unless ENVIRONMENT=local, against anything but this
machine, or with no seeded sample accounts.
"""

import itertools
import logging
import pathlib
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

# Run with `locust -f scripts/load_test.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from locust import HttpUser, between, events, task
from locust.env import Environment
from sqlalchemy import select

from app.core.config import settings
from app.core.taxonomy import NICHES
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns.models import Campaign

READ_BUDGET_MS = 300
WRITE_BUDGET_MS = 500
# Below this many requests a p95 is one or two slow requests, not a measure.
MIN_REQUESTS_FOR_P95 = 20
# The seed script's fake numbers (scripts/seed_dev_data.py, PHONE_PREFIX).
SAMPLE_PHONE_PREFIX = "+9190000"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
CITIES = ("Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem")

logger = logging.getLogger(__name__)
# Which campaign, niche or city to ask for next: a spread of traffic, not a
# secret, so the ordinary generator is right.
RNG = random.Random()  # noqa: S311 - a spread of traffic, not security


@dataclass(frozen=True)
class Person:
    headers: dict[str, str]
    # The brand's own campaigns; empty for a creator.
    campaign_ids: tuple[str, ...]
    handle: str | None
    # Published Passports to visit: only a published one is public (D-055).
    passports: tuple[str, ...] = ()


def _sample_people() -> tuple[list[Person], list[Person]]:
    """Every seeded sample brand and creator, each with a fresh access token."""
    now = datetime.now(UTC)
    with SessionLocal() as db:
        brands = db.execute(
            select(Account.id, Brand.id)
            .join(Brand, Brand.account_id == Account.id)
            .where(Account.phone.startswith(SAMPLE_PHONE_PREFIX))
        ).all()
        campaigns: dict[object, list[str]] = {}
        for brand_id, campaign_id in db.execute(
            select(Campaign.brand_id, Campaign.id).where(
                Campaign.brand_id.in_([brand_id for _, brand_id in brands])
            )
        ):
            campaigns.setdefault(brand_id, []).append(str(campaign_id))
        published = tuple(
            db.scalars(
                select(Creator.handle).where(
                    Creator.passport_published_at.is_not(None),
                    Creator.account_id.in_(
                        select(Account.id).where(
                            Account.phone.startswith(SAMPLE_PHONE_PREFIX)
                        )
                    ),
                )
            )
        )
        creators = db.execute(
            select(Account.id, Creator.handle)
            .join(Creator, Creator.account_id == Account.id)
            .where(Account.phone.startswith(SAMPLE_PHONE_PREFIX))
        ).all()

    def headers(account_id: object, role: str) -> dict[str, str]:
        token, _ = create_access_token(account_id, role, now)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {token}"}

    return (
        [
            Person(headers(account_id, "brand"), tuple(campaigns.get(brand_id, [])), None)
            for account_id, brand_id in brands
            if campaigns.get(brand_id)
        ],
        [
            Person(headers(account_id, "creator"), (), handle, published)
            for account_id, handle in creators
        ],
    )


BRANDS: itertools.cycle[Person] | None = None
CREATORS: itertools.cycle[Person] | None = None


@events.test_start.add_listener
def _refuse_anything_but_local(environment: Environment, **_: object) -> None:
    global BRANDS, CREATORS
    if settings.environment != "local":
        raise SystemExit("The load test runs only with ENVIRONMENT=local.")
    if urlparse(environment.host or "").hostname not in LOCAL_HOSTS:
        raise SystemExit("The load test runs only against this machine.")
    brands, creators = _sample_people()
    if not brands or not creators:
        raise SystemExit("No sample accounts: run scripts/seed_dev_data.py first.")
    RNG.shuffle(brands)
    RNG.shuffle(creators)
    BRANDS, CREATORS = itertools.cycle(brands), itertools.cycle(creators)
    logger.info("load_test.start brands=%d creators=%d", len(brands), len(creators))


class BrandUser(HttpUser):
    """A brand checking on its campaigns, its applicants and its money."""

    weight = 1
    # About 20 requests a minute: under every per-account limit, as a
    # person clicking through would be.
    wait_time = between(2, 4)

    def on_start(self) -> None:
        if BRANDS is None:
            raise RuntimeError("test_start did not run")
        self.person = next(BRANDS)

    def _get(self, path: str, name: str, **params: object) -> None:
        self.client.get(path, headers=self.person.headers, params=params, name=name)

    def _campaign(self) -> str:
        return RNG.choice(self.person.campaign_ids)

    @task(4)
    def my_campaigns(self) -> None:
        self._get("/api/v1/campaigns", "GET /campaigns")

    @task(4)
    def campaign_summary(self) -> None:
        self._get(
            f"/api/v1/campaigns/{self._campaign()}/summary", "GET /campaigns/{id}/summary"
        )

    @task(3)
    def applicants(self) -> None:
        self._get(
            f"/api/v1/campaigns/{self._campaign()}/applications",
            "GET /campaigns/{id}/applications",
        )

    @task(3)
    def search_creators(self) -> None:
        self._get(
            "/api/v1/creators",
            "GET /creators (search)",
            niche=RNG.choice(NICHES),
            city=RNG.choice(CITIES),
        )

    @task(2)
    def payments(self) -> None:
        self._get("/api/v1/payments/mine", "GET /payments/mine")
        self._get("/api/v1/payments/mine/totals", "GET /payments/mine/totals")

    @task(2)
    def deals(self) -> None:
        self._get("/api/v1/deal-memos/mine", "GET /deal-memos/mine")

    @task(1)
    def report(self) -> None:
        self._get(
            f"/api/v1/campaigns/{self._campaign()}/report", "GET /campaigns/{id}/report"
        )

    @task(2)
    def notifications(self) -> None:
        self._get("/api/v1/notifications/unread-count", "GET /notifications/unread-count")


class CreatorUser(HttpUser):
    """A creator looking for work and following their applications and deals."""

    weight = 4
    wait_time = between(2, 4)

    def on_start(self) -> None:
        if CREATORS is None:
            raise RuntimeError("test_start did not run")
        self.person = next(CREATORS)

    def _get(self, path: str, name: str, **params: object) -> None:
        self.client.get(path, headers=self.person.headers, params=params, name=name)

    @task(6)
    def discover(self) -> None:
        params = {"niche": RNG.choice(NICHES)} if RNG.random() < 0.5 else {}
        self._get("/api/v1/campaigns/discover", "GET /campaigns/discover", **params)

    @task(3)
    def for_me(self) -> None:
        self._get("/api/v1/campaigns/discover/for-me", "GET /campaigns/discover/for-me")

    @task(3)
    def my_applications(self) -> None:
        self._get("/api/v1/applications/me", "GET /applications/me")

    @task(2)
    def deals(self) -> None:
        self._get("/api/v1/deal-memos/mine", "GET /deal-memos/mine")

    @task(2)
    def passport(self) -> None:
        """Another creator's published Passport, as a brand's link opens it."""
        if not self.person.passports:
            return
        self._get(
            f"/api/v1/creators/by-handle/{RNG.choice(self.person.passports)}",
            "GET /creators/by-handle/{handle}",
        )

    @task(2)
    def attention(self) -> None:
        self._get("/api/v1/me/attention", "GET /me/attention")

    @task(1)
    def keep_availability(self) -> None:
        """Read the setting and put the same value back: a write that changes nothing."""
        current = self.client.get(
            "/api/v1/creators/me/availability",
            headers=self.person.headers,
            name="GET /creators/me/availability",
        )
        if current.status_code != 200:
            return
        self.client.put(
            "/api/v1/creators/me/availability",
            headers=self.person.headers,
            json={"booked_until": current.json().get("booked_until")},
            name="PUT /creators/me/availability",
        )


@events.quitting.add_listener
def _check_budgets(environment: Environment, **_: object) -> None:
    """Fail the run on any failed request or any p95 over its budget."""
    over = []
    for entry in environment.stats.entries.values():
        budget = READ_BUDGET_MS if entry.method == "GET" else WRITE_BUDGET_MS
        p95 = entry.get_response_time_percentile(0.95)
        verdict = "ok"
        if entry.num_requests < MIN_REQUESTS_FOR_P95:
            verdict = "too few to judge"
        elif p95 > budget:
            verdict = "OVER BUDGET"
            over.append(entry.name)
        print(
            f"{entry.name:42} n={entry.num_requests:6} p95={p95:6.0f} ms "
            f"budget={budget} ms failures={entry.num_failures:4} {verdict}"
        )
    failures = environment.stats.total.num_failures
    if over or failures:
        print(f"FAILED: {len(over)} over budget, {failures} failed requests")
        environment.process_exit_code = 1
