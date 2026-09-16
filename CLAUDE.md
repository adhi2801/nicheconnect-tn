# CLAUDE.md

## Project

NicheConnect TN — a Tamil Nadu-focused brand↔creator marketplace. This repo is the backend only (FastAPI). A brand-facing web dashboard already exists separately as a Figma Make prototype (React/Vite/TypeScript) and will be wired to this backend. A creator-facing mobile app (React Native) comes later, after this backend exists.

## Current phase

Foundation build. Two developers working in parallel:

- one on the data layer (schema, migrations, pgvector)
- one on the API skeleton (auth, endpoints, CI)

## Non-negotiable constraints — do not violate these even if asked

- This service must never receive, pool, or hold campaign funds. Brand pays creator directly (UPI/bank transfer). This service only tracks `PaymentStatus` (was it paid, when, how much). Never use the words "escrow", "wallet", "guaranteed funds", or "split settlement" anywhere in code, comments, commit messages, or copy.
- Keep raw PII (phone numbers, bank details) out of anything embedded in pgvector — use an internal ID instead.
- Every schema change goes through an Alembic migration. Never hand-edit the database.
- Every public endpoint needs rate limiting.
- An endpoint isn't done until it has a passing test.

## Architecture

- Modular monolith — one deployable FastAPI app, not microservices.
- Modules: `app/modules/{auth, matching, deal_memo, payment_status, notifications}`
- DB: PostgreSQL + pgvector. Cache/queue: Redis. Migrations: Alembic.
- Core tables: Brand, Creator, Campaign, Application, DealMemo, PaymentStatus.
- Matching (once built): SentenceTransformers embeddings + pgvector cosine similarity — same pattern proven in the InterviewCoach AI project.
- External calls (WhatsApp, Claude API): structured retry-with-backoff, same pattern as above.

## Commands

```bash
docker compose up -d                          # Postgres (pgvector) + Redis
pip install -r requirements.txt
uvicorn app.main:app --reload                 # http://localhost:8000/healthz
alembic revision --autogenerate -m "message"
alembic upgrade head
pytest
```

## Working rules

- Work in small, verified steps: implement → run the tests → confirm they pass before moving to the next thing. Don't write five files and hope.
- Every merge to `main` goes through a pull request the other developer reviews.
- Don't add a new dependency without flagging it to the other developer — keep `requirements.txt` intentional, not accumulated.
- Compliance context (DPDP, ASCI disclosure, TDS/GST) lives in the project's validation pack, not in this file — ask before assuming a compliance detail rather than guessing.

## Quality bar — do not settle

- One file, one job. Never combine multiple modules, models, or unrelated responsibilities into a single file for convenience. Follow the existing `app/modules/<name>/` structure — each module owns its own files.
- Change or create ONE file at a time. Show it, explain what it does, wait for confirmation it's correct (tests passing, behavior verified) before moving to the next file. Never generate a whole project or a large batch of files in one shot and call it done.
- Never ship a shortcut silently. If something is ambiguous, or the "fast" way conflicts with a rule in this file, stop and ask rather than quietly picking the easier option.
- Every new function/endpoint gets a real test, not a placeholder. "It runs" is not the bar — "it's tested and handles the obvious failure cases" is.
- Re-read the "Non-negotiable constraints" section above before touching anything related to payments, PII, or embeddings. These are not suggestions.
- Never claim something was tested, run, or verified unless it actually was. Say "this should work" for a reasoned expectation; say "verified — tests pass" only after actually running it.
- Before a hard-to-reverse choice (database technology, core data model, hosting provider, folder architecture), say what you're about to do and why in one line before doing it — don't silently commit to it.