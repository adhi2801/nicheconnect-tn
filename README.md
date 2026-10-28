# NicheConnect TN — Backend

[![CI](https://github.com/adhi2801/nicheconnect-tn/actions/workflows/ci.yml/badge.svg)](https://github.com/adhi2801/nicheconnect-tn/actions/workflows/ci.yml)

FastAPI backend for NicheConnect TN. Modular monolith — one deployable app,
clean internal module boundaries. No campaign funds ever pass through this
service; it tracks payment **status** only (brand pays creator directly).

## Modules
- `app/core` — what every module shares: errors, rate limits, idempotency, the clock, and the link and text checks that keep people safe from each other (items 57, 60)
- `app/modules/auth` — brand + creator accounts (adults only, D-086), login codes and sessions, profiles, the Creator Passport and rate card, availability (D-083), creator search, blocking (item 59), the admin side, data export
- `app/modules/campaigns` — campaigns, applications, and invitations with "work together again" (D-016, D-084)
- `app/modules/matching` — matching both ways, with reasons (Qwen3-Embedding + pgvector, D-052)
- `app/modules/deal_memo` — deal memos, proof (links and files, cleaned and sealed), results read from proof, and the tamper-evident deal record (D-057, D-065, D-070)
- `app/modules/payment_status` — payment status tracking only, never funds; the UPI pay link that opens the brand's own app (D-085)
- `app/modules/disputes` — dispute timelines: we record, we do not judge (D-028, D-035)
- `app/modules/notifications` — in-app notifications; login codes by WhatsApp (D-058)

## Where to look first
- `CLAUDE.md` — the operating manual and the constraints that never bend
- `docs/README.md` — **the map of every document: what each is for and when to read it**
- `docs/BACKEND_COMPLETE.md` — what is left before the frontend starts
- `docs/DECISIONS.md` — every approved decision, append-only
- `docs/standards/` — the bar, read before working in an area: backend, database, security, testing, legal, trust and safety, UX and frontend
- `docs/COMPETITIVE_LANDSCAPE.md`, `docs/REVENUE_RESEARCH.md`, `docs/GO_TO_MARKET.md`, `docs/SURVIVAL_PLAYBOOK.md`, `docs/PSYCHOLOGY_AND_TRUST.md` — what we build, why, how it reaches people, and how the company survives
- `SECURITY.md` and `docs/INCIDENT_RESPONSE.md` — how to report a vulnerability, and what we do when something goes wrong
- `infra/README.md` — AWS, described in code, and the steps to go live

## Local setup (same for both of you)

```bash
cp .env.example .env          # fill in real values, never commit .env
docker compose up -d          # starts Postgres (pgvector) + Valkey
uv sync                       # installs Python 3.14 and exactly what uv.lock pins (D-072)
uv run uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/healthz` → `{"status": "ok"}`

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

Never edit the database by hand — every schema change goes through a migration.

## Tests

```bash
uv run pytest
```

Tests roll back everything they create, so they can run against a database
that already holds sample data.

## Sample data and performance

```bash
uv run python scripts/seed_dev_data.py --reset          # realistic Tamil Nadu data
uv run python scripts/measure_performance.py --explain  # p95 per list endpoint + query plans
uv run python scripts/dev_login.py +919000000001        # an access token for a sample account
```

All three refuse to run unless `ENVIRONMENT=local`. Login codes are never
logged, so `dev_login.py` is how to call the API as a signed-in brand or
creator on a laptop: it prints only the token, so
`$token = uv run python scripts\dev_login.py +919000000001` captures it (D-059).

Sample phones are
`+9190000xxxxx` and emails end in `@example.com`, so no sample row can ever
be mistaken for a real person. `--reset` removes the previous sample data.

## Working rules
- Read the standard for the area before changing it (`CLAUDE.md` section 7.0).
- Every merge to `main` goes through a pull request the other person reviews, with CI green: tests, types, lint, migrations, contract fuzzing, coverage, dependency, licence and image checks, the infrastructure files and every document's references (`docs/standards/testing.md` section 9).
- Secrets live in `.env` (gitignored) or a shared password manager — never in git.
- Decisions and their reasons go in `docs/DECISIONS.md`, in the same commit as the work they approve.
