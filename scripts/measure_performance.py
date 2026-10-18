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
import uuid

# Run as `python scripts/measure_performance.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collections import defaultdict
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.storage import get_file_store
from app.db.session import SessionLocal, engine, get_db
from app.main import app
from app.modules.auth import second_factor, second_factor_secrets
from app.modules.auth import service as login
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import (
    PHONE_CHANGE_WAIT,
    AccountPhoneChange,
)
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.totp_factor import TotpFactor
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import (
    TWO_FACTORS,
    create_access_token,
    decode_access_token,
    hash_otp_code,
)
from app.modules.campaigns.models import Campaign
from app.modules.me import data_export_service, phone_change_service
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


# Kept low on purpose. Every request here runs in a savepoint of one
# transaction that is rolled back, and each bulk row adds a savepoint of its
# own, so the rounds pile hundreds of subtransactions into one transaction.
# Past 64, PostgreSQL's visibility checks slow down, and each round reads
# slower than the last: 292 ms rising to 477 ms over 20 rounds on
# 30 September. The same 20 rounds with every request committed, as in
# production, stayed flat at 269-341 ms. A slow bulk number here is worth
# re-checking with real commits before it is believed.
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
    4. `deals` reports, by that same creator, each about a different
       campaign: a second report of the same thing only returns the first;
       then the admin's queue and its clocks, `deals` times each (item 51).
    5. Those campaigns withheld on an order, the takedown lists and discovery
       read with them in place, then each lifted (item 52).
    6. `deals` rounds of the second check (item 82): a code asked for and a
       UPI ID set with it, read back and its wait cancelled; the export
       asked for, built by the job and downloaded (D-111), and logging out
       everywhere, each with its own code.
    7. `deals` phone number changes (item 80), each with both codes, read
       and cancelled; then `deals` runs of the job, each making one change.
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
        if timed:
            # A read, timed here because only these deals have agreed dates
            # (item 69); the seeded data has no accepted deal.
            limiter.reset()
            started = time.perf_counter()
            calendar = client.get(f"{memos}/{memo}/calendar.ics", headers=creator_headers)
            timings["GET /deal-memos/{id}/calendar.ics"].append(
                (time.perf_counter() - started) * 1000
            )
            if calendar.status_code != 200:
                raise SystemExit(f"calendar.ics: {calendar.status_code}")
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

        reported = db.scalars(select(Campaign.id).limit(deals)).all()
        for campaign_id in reported:
            write(
                "POST /reports",
                "/api/v1/reports",
                rate_card_headers,
                {
                    "subject_kind": "campaign",
                    "subject_id": str(campaign_id),
                    "category": "spam",
                    "note": "Measured, then rolled back.",
                },
            )

        # The admin's queue and its clocks (item 51), with those reports in it.
        admin = Account(phone="+919000099998", role="admin")
        db.add(admin)
        db.flush()
        admin_token, _ = create_access_token(admin.id, "admin", now, methods=TWO_FACTORS)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # The admins' login with two factors (item 101), once per report: a
        # fresh phone code each round, and the factor's last step cleared
        # between rounds, since this script's clock stands still and each
        # authenticator code works once.
        secret = bytes(range(20))
        factor = TotpFactor(
            account_id=admin.id,
            secret_ciphertext=second_factor_secrets.seal(secret, admin.id),
            enrolled_at=now,
        )
        db.add(factor)
        db.flush()
        for round_number, _ in enumerate(reported, start=1):
            factor.last_used_step = None
            db.add(
                OtpChallenge(
                    phone=admin.phone,
                    code_hash=hash_otp_code("135790"),
                    expires_at=now + timedelta(minutes=5),
                    created_at=now + timedelta(microseconds=round_number),
                    updated_at=now,
                )
            )
            db.flush()
            write(
                "POST /auth/admin/login",
                "/api/v1/auth/admin/login",
                {},
                {
                    "phone": admin.phone,
                    "code": "135790",
                    "authenticator_code": second_factor.code_at_step(
                        secret, second_factor.step_at(now)
                    ),
                },
            )
        for _ in reported:
            write(
                "GET /admin/reports (queue)",
                "/api/v1/admin/reports",
                admin_headers,
                method="GET",
            )
            write(
                "GET /admin/reports/clocks",
                "/api/v1/admin/reports/clocks",
                admin_headers,
                method="GET",
            )

        # A brand's domain (item 74): claimed, a check asked for, read back.
        # The check itself runs in the background job, never in a request.
        for round_number, _ in enumerate(reported, start=1):
            write(
                "POST /brands/me/domain",
                "/api/v1/brands/me/domain",
                brand_headers,
                {"domain": f"measured{round_number}.in"},
            )
            write(
                "POST /brands/me/domain/check",
                "/api/v1/brands/me/domain/check",
                brand_headers,
            )
            write(
                "GET /brands/me/domain",
                "/api/v1/brands/me/domain",
                brand_headers,
                method="GET",
            )

        # Takedowns (item 52): each reported campaign withheld on an order,
        # the lists read with them in place, discovery read past them, and
        # each lifted again.
        takedowns = []
        for campaign_id in reported:
            takedowns.append(
                write(
                    "POST /admin/takedowns",
                    "/api/v1/admin/takedowns",
                    admin_headers,
                    {
                        "subject_kind": "campaign",
                        "subject_id": str(campaign_id),
                        "basis": "court_order",
                        "issued_by": "High Court of Madras",
                        "order_reference": "WP 1012 of 2026",
                        "received_at": (now - timedelta(hours=1)).isoformat(),
                        "note": "Measured, then rolled back.",
                    },
                )
            )
        owner = db.scalar(
            select(Brand.account_id)
            .join(Campaign, Campaign.brand_id == Brand.id)
            .where(Campaign.id == reported[0])
        )
        owner_token, _ = create_access_token(owner, "brand", now)
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        for _ in takedowns:
            write(
                "GET /admin/takedowns",
                "/api/v1/admin/takedowns?active=true",
                admin_headers,
                method="GET",
            )
            write(
                "GET /me/takedowns",
                "/api/v1/me/takedowns",
                owner_headers,
                method="GET",
            )
            write(
                "GET /campaigns/discover (with takedowns)",
                "/api/v1/campaigns/discover",
                creator_headers,
                method="GET",
            )
        for takedown in takedowns:
            write(
                "POST /admin/takedowns/{id}/lift",
                f"/api/v1/admin/takedowns/{takedown['id']}/lift",
                admin_headers,
                {"note": "Measured, then rolled back."},
            )

        # The second check (item 82). The phone's caps, like the limiter,
        # are not what is measured, so they are lifted for the run; the
        # code is read from a fake sender, as in the tests.
        sender = FakeOtpSender()
        app.dependency_overrides[get_otp_sender] = lambda: sender
        caps, login.OTP_SEND_LIMITS = login.OTP_SEND_LIMITS, ((timedelta(days=1), 10**6),)
        notice, settings.upi_notice_version = settings.upi_notice_version, "measured"
        creator_id = decode_access_token(
            creator_headers["Authorization"].removeprefix("Bearer "), now
        ).account_id
        phone = db.get_one(Account, creator_id).phone

        def with_code(name: str, action: str, **fields: str) -> dict:
            write(
                name, "/api/v1/me/step-up", creator_headers, {"action": action, **fields}
            )
            return {**creator_headers, "Step-Up-Code": sender.last_code_for(phone) or ""}

        try:
            for round_number in range(deals):
                upi_id = f"measured{round_number}@okaxis"
                write(
                    "PUT /creators/me/upi (with its code)",
                    "/api/v1/creators/me/upi",
                    with_code("POST /me/step-up", "set_upi_id", upi_id=upi_id),
                    {"upi_id": upi_id, "consent": True, "notice_version": "measured"},
                    method="PUT",
                )
                write(
                    "GET /creators/me/upi",
                    "/api/v1/creators/me/upi",
                    creator_headers,
                    method="GET",
                )
                write(
                    "DELETE /creators/me/upi/waiting",
                    "/api/v1/creators/me/upi/waiting",
                    creator_headers,
                    method="DELETE",
                )
                # The export (D-111): asked for, built by the job, then
                # downloaded once, each step timed on its own.
                asked = write(
                    "POST /me/exports (with its code)",
                    "/api/v1/me/exports",
                    with_code("POST /me/step-up", "download_export"),
                )
                started = time.perf_counter()
                data_export_service.run_exports(
                    lambda: nullcontext(db), get_file_store(), now
                )
                timings["job: one data export built"].append(
                    (time.perf_counter() - started) * 1000
                )
                download_headers = with_code(
                    "POST /me/step-up", "download_export", export_id=asked["id"]
                )
                write(
                    "POST /me/exports/{id}/download (with its code)",
                    f"/api/v1/me/exports/{asked['id']}/download",
                    download_headers,
                )
                write(
                    "POST /auth/logout-all (with its code)",
                    "/api/v1/auth/logout-all",
                    with_code("POST /me/step-up", "log_out_everywhere"),
                )

            # Changing the phone number (item 80): both codes, the change, a
            # read and the cancel; then the job making one due change, on an
            # account made for it, timed as one whole run.
            for _ in range(deals):
                new_phone = f"+9197{uuid.uuid4().int % 10**8:08d}"
                current = with_code(
                    "POST /me/step-up", "change_phone", new_phone=new_phone
                )
                write(None, "/api/v1/auth/otp/request", {}, {"phone": new_phone})
                write(
                    "POST /me/phone-change (with both codes)",
                    "/api/v1/me/phone-change",
                    current,
                    {
                        "new_phone": new_phone,
                        "new_phone_code": sender.last_code_for(new_phone) or "",
                    },
                )
                write(
                    "GET /me/phone-change",
                    "/api/v1/me/phone-change",
                    creator_headers,
                    method="GET",
                )
                write(
                    "DELETE /me/phone-change",
                    "/api/v1/me/phone-change",
                    creator_headers,
                    method="DELETE",
                )
                # The same without the current number (D-110), then cancelled.
                lost_phone = f"+9197{uuid.uuid4().int % 10**8:08d}"
                write(None, "/api/v1/auth/otp/request", {}, {"phone": lost_phone})
                write(
                    "POST /me/phone-change/without-current-number",
                    "/api/v1/me/phone-change/without-current-number",
                    creator_headers,
                    {
                        "new_phone": lost_phone,
                        "new_phone_code": sender.last_code_for(lost_phone) or "",
                    },
                )
                write(None, "/api/v1/me/phone-change", creator_headers, method="DELETE")
            for _ in range(deals):
                moving = Account(
                    phone=f"+9196{uuid.uuid4().int % 10**8:08d}", role="creator"
                )
                db.add(moving)
                db.flush()
                db.add(
                    AccountPhoneChange(
                        account_id=moving.id,
                        new_phone=f"+9195{uuid.uuid4().int % 10**8:08d}",
                        requested_at=now - PHONE_CHANGE_WAIT,
                        takes_effect_at=now,
                    )
                )
                db.commit()
                started = time.perf_counter()
                run = phone_change_service.run_changes(lambda: nullcontext(db), now)
                timings["job: one phone change made"].append(
                    (time.perf_counter() - started) * 1000
                )
                if run.made != 1:
                    raise SystemExit(f"phone change job: {run}")
        finally:
            login.OTP_SEND_LIMITS = caps
            settings.upi_notice_version = notice
            app.dependency_overrides.pop(get_otp_sender, None)
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        outer.rollback()
        connection.close()

    return [
        summarise(
            name, values, READ_BUDGET_MS if name.startswith("GET ") else WRITE_BUDGET_MS
        )
        for name, values in timings.items()
    ]


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
    # Logged in two months ago, as a seeded creator would be: changing a
    # phone number asks for a login a week old, or 30 days without the
    # current number (D-109, D-110).
    creator_token, _ = create_access_token(
        creator.account_id, "creator", now, authenticated_at=now - timedelta(days=60)
    )
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
        # A reporter's own reports and what became of each (item 102).
        measure(
            client,
            "GET /reports/mine",
            "GET",
            "/api/v1/reports/mine",
            brand_headers,
            args.runs,
            READ_BUDGET_MS,
        ),
        # Creator search: the query a brand runs most. Each filter joins or
        # scans something different, so each shape is timed on its own.
        *(
            measure(
                client,
                name,
                "GET",
                f"/api/v1/creators{query}",
                brand_headers,
                args.runs,
                READ_BUDGET_MS,
            )
            for name, query in (
                ("GET /creators (search, no filter)", ""),
                ("GET /creators?niche&city", "?niche=food&city=Madurai"),
                (
                    "GET /creators?platform&followers",
                    "?platform=instagram&min_followers=10000&max_followers=100000",
                ),
                (
                    "GET /creators?max_price&format",
                    "?max_price_paise=1500000&format=reel",
                ),
                ("GET /creators?q (words)", "?q=food"),
            )
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
