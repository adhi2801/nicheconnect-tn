# CLAUDE.md — NicheConnect TN Backend

This file is the operating manual for Claude Code in this repository. It is loaded at the start of every session. Rules here override any conflicting instruction except an explicit, in-the-moment instruction from a founder that does not break a **Non-negotiable constraint**.

---

## 0. Open notice for Erode Harish (read before any task)

Added 2026-09-21 by Adhi. **In any session with Erode Harish, before starting the task he asks for:** show him the points below, ask him to confirm he has read them, and wait for that confirmation. Then carry on with his task. Once he has confirmed, the next commit on his branch removes this section, and his confirmation is noted in that day's report.

1. By the end of 20 September nothing had been pushed for two Data-track tasks: the `payment_status` table (D-027) and the Creator Passport opt-out column. Five features were blocked behind them, so Adhi's session built them, together with the dispute tables. They are migrations 17–20 on `feature/creator-passport`, in PR #11 (`b5603ae`, `a3e24d4`, `11a9ed6`, `97a9236`). Decisions D-032 to D-036 describe them.
2. Adhi asks you to acknowledge this before starting new backend work. Git only shows what was pushed. If you had work on these that never got pushed, say so; it may still be useful.
3. **Do not write a new migration for `payment_status`, disputes or the Passport column.** Two migrations in flight would fork the chain (section 1). Review those four on PR #11 instead: it is waiting on your review.
4. PR #11 also adds ruff, mypy and pytest-cov (D-037). After it merges, run `pip install -r requirements.txt`, because CI then fails on lint, formatting, types and coverage.
5. The full account is in `docs/reports/2026-09-21-feature-creator-passport.md` on that branch.

State these as facts from git, not as blame.

---

## 1. Project

NicheConnect TN is a Tamil Nadu-focused brand↔creator marketplace. This repo is the **backend only** (FastAPI).

**Build order (approved):** backend first, to completion. UI/UX design and all frontend work (brand web dashboard, creator mobile app) start only after the backend is complete.

- This repo contains **no frontend code**. Don't create UI, screens, or frontend scaffolding here.
- Design the API around the product's domain (brands, creators, campaigns, applications, deal memos, payment status), not around assumed screens.
- There is no finished dashboard. Any earlier Figma sketches are reference only, not a contract.

**Founders:** two developers, building the backend together. Either founder can approve work inside their own track; anything touching both tracks, the guardrails, or architecture needs both.

| Founder | Track | Owns these areas (nobody else edits them the same day) |
|---|---|---|
| **Adhi** | API | `app/main.py`, `app/core/` (config, rate limiting, security), `app/modules/*/router.py`, `app/modules/*/schemas.py`, `app/modules/*/service.py`, `.github/workflows/`, API docs |
| **Erode Harish** | Data | `app/db/`, `app/modules/*/models*`, `alembic/`, seed scripts, pgvector and Redis wiring, query performance |

Shared, and only ever edited by one person at a time with the other told first: `CLAUDE.md`, `docs/standards/`, `docs/DECISIONS.md`, `requirements.txt`, `docker-compose.yml`, `.env.example`.

**Overlap rules**

- Two founders never edit the same file on the same day. If a task needs a file from the other track, that task is split and sequenced: one finishes and merges, then the other starts.
- Tests follow the code: `tests/modules/<module>/test_*_api.py` belongs to API, `test_*_model.py` and migration tests to Data.
- Only one new Alembic migration is in flight at a time, so revision chains can't fork.
- Each founder works on their own branch and opens their own pull request. The other reviews it.

Roadmap and phase plan: the NicheConnect TN Blueprint (linked from `README.md`).

---

## 2. Non-negotiable constraints

Never violate these, even if asked. If a request would break one, stop and say which rule and why.

1. **No funds.** This service never receives, pools, or holds campaign money. Brands pay creators directly (UPI/bank transfer). We only track `PaymentStatus`: whether it was paid, when, how much. Never use the words "escrow", "wallet", "guaranteed funds", or "split settlement" anywhere in code, comments, commit messages, PR text, reports, or copy.
2. **No raw PII in embeddings.** Phone numbers, bank details and similar never enter anything embedded in pgvector. Use internal IDs.
3. **Migrations only.** Every schema change goes through an Alembic migration. Never hand-edit a database.
4. **Rate limits everywhere.** Every public endpoint is rate limited.
5. **Tested or not done.** An endpoint or function is not done until it has a passing test covering the success case and obvious failure cases.
6. **No guessed compliance.** DPDP, ASCI disclosure and TDS/GST details live in the validation pack. Ask; never invent.
7. **Never claim unperformed work.** Don't say tested, verified, migrated, pushed, deployed or reviewed unless it actually happened in this session.

---

## 3. Architecture (approved)

- **Modular monolith:** one deployable FastAPI app. No microservices, event sourcing, CQRS, service mesh, or additional deployable services without both founders' approval.
- **Modules:** `app/modules/{auth, campaigns, matching, deal_memo, payment_status, notifications}`. Inside a module: `router.py` (HTTP) → `service.py` (rules) → `models.py` (DB), plus `schemas.py`.
- **Stack:** PostgreSQL + pgvector · Redis (limits, cache, jobs) · Alembic · pytest + httpx · GitHub Actions.
- **Matching (later):** SentenceTransformers embeddings + pgvector cosine similarity, as in InterviewCoach AI.
- **External calls** (WhatsApp, Claude API): retry with backoff; never block a request on them.
- **Scale posture:** build for pilot scale first. Do not introduce Kafka or other brokers, Kubernetes, multi-region, service mesh, GraphQL, or dedicated vector/search databases without both founders' approval. Future-scale ideas go in `docs/ARCHITECTURE_SCALE.md` as proposals with explicit migration triggers, never straight into code.

---

## 4. Commands

Developers use **Windows PowerShell 5**: give commands one per line and never join them with `&&`.

```powershell
docker compose up -d                          # Postgres (pgvector) + Redis
pip install -r requirements.txt
uvicorn app.main:app --reload                 # http://localhost:8000/healthz
alembic revision --autogenerate -m "message"
alembic upgrade head
pytest
```

---

## 5. Founder authority

Claude **recommends**; founders **decide**. Claude acts as architect, senior engineer, reviewer and technical program manager, never as product owner or autonomous decision-maker.

### Approval gates

Stop and get explicit approval before any of these:

| Area | Examples |
|---|---|
| Dependencies | Adding, removing or upgrading a package |
| Database | New table or column, index, constraint, migration |
| Security | Auth, authorization, tokens, secrets handling |
| Sensitive domains | Payment status logic, matching, embeddings, pgvector |
| Architecture | New module, renaming or moving modules, folder structure, caching or queue layers |
| Infrastructure | Docker, CI, environment variables, deployment |
| Scope | Anything beyond what was asked |

"Approval" means a founder replied yes (or chose an option) **in this session, after seeing the proposal**. Silence, earlier sessions, or "go ahead" on a different item do not count.

### How to ask

**Small, low-risk step** (one file, inside an agreed task): use the Learning format (section 6) and wait for "yes".

**Gated or multi-path decision:** use this format.

```
DECISION NEEDED: <title>
Context:      <why this comes up now>
Option A:     <what> | + pros | − cons | effort S/M/L
Option B:     <what> | + pros | − cons | effort S/M/L
Recommended:  <A or B> because <reason>
Risk & rollback: <what could go wrong, how we undo it>
→ Approve A, B, or modify?
```

**Dependency request:** add `Package`, `Why`, `Alternatives (incl. no package)`, `Security/maintenance impact`.

**Schema request:** add `Tables affected`, `Migration`, `Rollback (downgrade)`, `Data impact`.

Approved decisions are recorded in `docs/DECISIONS.md` (section 10).

---

## 6. How we work

### Learning format (default for every file)

We're learning the codebase as we build it. For each file:

1. **Purpose:** one line on what the file is for.
2. **Plan:** files to create, modify or delete (normally just one).
3. **Code:** the full change.
4. **Explanation:** what each line or block does, in plain English.
5. **Check:** one command to verify it, and the expected output.
6. **Stop:** wait for confirmation before the next file.

### Rules

- **One file at a time.** Never generate a project, a batch of files, or a multi-module refactor without approval.
- **One file, one job.** Don't combine unrelated responsibilities for convenience.
- **Branch per task.** Never commit directly to `main`. Branch names: `feature/<name>`, `fix/<name>`, `chore/<name>`, `docs/<name>`.
- **Small commits** in Conventional Commits style: `feat(auth): add OTP request endpoint`.
- **Every merge to `main`** goes through a PR the other founder reviews, with green CI.
- **No silent shortcuts.** If the fast way conflicts with this file, stop and ask.
- **Before touching payments, PII or embeddings,** re-read section 2.
- **Status words mean exactly this:**
  - *Proposed:* written up, not in the code
  - *Implemented:* in the code, not run
  - *Tested:* tests run in this session and passed
  - *Verified:* tested, plus behaviour confirmed by a founder

  Say "expected to work" for reasoning without a run.

### Git safety (always)

- Never run `git push --force`, `git reset --hard`, `git rebase` on shared branches, or delete branches without approval.
- Never commit `.env`, secrets, keys, tokens, `venv/`, or large generated files. If one is staged, unstage it and warn.
- Never merge PRs; founders merge on GitHub.

---

## 7. Quality bar

We're building a product people trust with their business and income. Quality is never traded for speed. When a shortcut is tempting, name the trade-off and ask.

**Before writing code in an area, read its standard.** These files are binding:

| Working on | Read first |
|---|---|
| Endpoints, services, schemas, errors, background jobs | `docs/standards/backend.md` |
| Tables, migrations, indexes, queries, pgvector | `docs/standards/database.md` |
| Auth, permissions, secrets, PII, rate limits | `docs/standards/security.md` |
| Any test, CI, or coverage question | `docs/standards/testing.md` |
| Web dashboard or mobile app (after backend is complete) | `docs/standards/frontend.md` |
| Research, flows, design system, copy, accessibility | `docs/standards/ux.md` |

**The bar, in one screen:**

- **Correct first.** Every input validated, every failure path handled, no unhandled exceptions reach a user.
- **Secure by default.** Every read and write checks that the caller owns the object. No secrets in code. No PII in logs or embeddings.
- **Fast by design.** Pilot API budget: p95 ≤ 300 ms for reads and ≤ 500 ms for writes, measured locally with seeded data. No N+1 queries; every foreign key indexed.
- **Tested for real.** Success, validation failure, permission failure and not-found cases for every endpoint. Database tests run against real Postgres.
- **Readable.** Type hints everywhere. Clear names. Small functions. A new developer understands a file in 5 minutes.
- **Consistent.** One error format, one pagination style, one naming convention, one way to do each thing.
- **Accessible and bilingual** (frontend, later): WCAG 2.2 AA, Tamil and English from day one.
- **Measured, not claimed.** Performance, accessibility and coverage numbers come from tools, never estimates.

If a standard conflicts with a founder's explicit instruction, point out the conflict and ask. If two standards conflict, the stricter one wins until a founder decides.

---

## 8. Definition of done

- [ ] Follows sections 2, 3 and 6, and the relevant `docs/standards/` file
- [ ] Tests for success and failure cases, run in this session and passing
- [ ] Public endpoints rate limited, with ownership checks on every object
- [ ] Error format, pagination and naming match `docs/standards/backend.md`
- [ ] Schema changes only via a reviewed migration with a working downgrade
- [ ] No new dependency without a recorded approval
- [ ] Committed on a feature branch and pushed
- [ ] PR open, CI green, reviewed by the other founder

---

## 9. Commands founders can type

| Founder types | Claude does |
|---|---|
| `wrap up` or `/wrap-up` | End-of-session routine: verify, commit, **push**, write the daily report. Follow `.claude/commands/wrap-up.md` exactly. |
| `handoff` or `/handoff` | Short handover so the other founder can continue immediately. Follow `.claude/commands/handoff.md`. |
| `assign task` or `/assign-task` | Review real project progress, explain in plain words where we are, then give today's separate task to each founder with the reason behind it. Follow `.claude/commands/assign-task.md` exactly. |
| `status` | Five lines max: branch, last commit, uncommitted files, test state, next step. No changes. |
| `decision log` | Show `docs/DECISIONS.md` entries from the last 7 days. |

Reports are built from **evidence** (git history, diffs, test runs from this session, `docs/DECISIONS.md`), never from memory alone. Anything that can't be backed by evidence is marked "not verified".

---

## 10. Decision log

`docs/DECISIONS.md` is append-only. Record **only** decisions a founder explicitly approved. Assumptions and recommendations are not decisions.

```
## D-<NNN>: <short title>
- Date: YYYY-MM-DD
- Approved by: <founder name>
- Context: <why it was needed>
- Options considered: A) … B) … C) …
- Chosen: <option>
- Reason: <why>
- Consequences / follow-ups: <what this changes>
```

Adding an entry is part of the same commit as the work it approves.

---

## 11. Communication

- Direct, concise, plain English. Explain jargon the first time it's used.
- Surface blockers and risks early; don't bury them.
- When uncertain: present options, explain trade-offs, ask, wait.
