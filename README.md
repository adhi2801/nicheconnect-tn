# NicheConnect TN — Backend

FastAPI backend for NicheConnect TN. Modular monolith — one deployable app,
clean internal module boundaries. No campaign funds ever pass through this
service; it tracks payment **status** only (brand pays creator directly).

## Modules
- `app/modules/auth` — brand + creator accounts, login codes and sessions, profiles, the Creator Passport and rate card, creator search, the admin side, data export
- `app/modules/campaigns` — campaigns and applications (D-016)
- `app/modules/matching` — matching both ways, with reasons (Qwen3-Embedding + pgvector, D-052)
- `app/modules/deal_memo` — deal memos, proof (links and files, cleaned and sealed), results read from proof, and the tamper-evident deal record (D-057, D-065, D-070)
- `app/modules/payment_status` — payment status tracking only, never funds
- `app/modules/disputes` — dispute timelines: we record, we do not judge (D-028, D-035)
- `app/modules/notifications` — in-app notifications; login codes by WhatsApp (D-058)

## Where to look first
- `CLAUDE.md` — the operating manual and the constraints that never bend
- `docs/BACKEND_COMPLETE.md` — what is left before the frontend starts
- `docs/DECISIONS.md` — every approved decision, append-only
- `docs/standards/` — the bar for backend, database, security, testing, UX and frontend
- `docs/PRODUCT_BACKLOG.md`, `docs/COMPETITIVE_LANDSCAPE.md`, `docs/REVENUE_RESEARCH.md`, `docs/GO_TO_MARKET.md`, `docs/PSYCHOLOGY_AND_TRUST.md` — what we build, why, and how it reaches people
- `infra/README.md` — AWS, described in code, and the steps to go live

## Local setup (same for both of you)

```bash
cp .env.example .env          # fill in real values, never commit .env
docker compose up -d          # starts Postgres (pgvector) + Valkey
pip install -r requirements-dev.txt   # the app, plus the tools that check it
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/healthz` → `{"status": "ok"}`

## Migrations

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

Never edit the database by hand — every schema change goes through a migration.

## Tests

```bash
pytest
```

Tests roll back everything they create, so they can run against a database
that already holds sample data.

## Sample data and performance

```bash
python scripts/seed_dev_data.py --reset          # realistic Tamil Nadu data
python scripts/measure_performance.py --explain  # p95 per list endpoint + query plans
python scripts/dev_login.py +919000000001        # an access token for a sample account
```

All three refuse to run unless `ENVIRONMENT=local`. Login codes are never
logged, so `dev_login.py` is how to call the API as a signed-in brand or
creator on a laptop: it prints only the token, so
`$token = python scripts\dev_login.py +919000000001` captures it (D-059).

Sample phones are
`+9190000xxxxx` and emails end in `@example.com`, so no sample row can ever
be mistaken for a real person. `--reset` removes the previous sample data.

## Working rules
- Every merge to `main` goes through a pull request the other person reviews.
- Secrets live in `.env` (gitignored) or a shared password manager — never in git.
- Decisions and their reasons go in `docs/DECISIONS.md`, in the same commit as the work they approve.
