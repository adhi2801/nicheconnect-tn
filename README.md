# NicheConnect TN — Backend

FastAPI backend for NicheConnect TN. Modular monolith — one deployable app,
clean internal module boundaries. No campaign funds ever pass through this
service; it tracks payment **status** only (brand pays creator directly).

## Modules
- `app/modules/auth` — brand + creator accounts, login/session
- `app/modules/matching` — creator–brand matching (SentenceTransformers + pgvector)
- `app/modules/deal_memo` — deal memo generation, ASCI disclosure, usage rights
- `app/modules/payment_status` — payment status tracking only, never funds
- `app/modules/notifications` — WhatsApp / email reminders

## Local setup (same for both of you)

```bash
cp .env.example .env          # fill in real values, never commit .env
docker compose up -d          # starts Postgres (pgvector) + Redis
pip install -r requirements.txt
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

## Working rules
- Every merge to `main` goes through a pull request the other person reviews.
- Secrets live in `.env` (gitignored) or a shared password manager — never in git.
- Decisions and schema rationale go in the shared team doc, linked here: `<add link>`.
