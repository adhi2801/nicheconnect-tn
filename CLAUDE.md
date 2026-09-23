# CLAUDE.md — NicheConnect TN Backend

This file is the operating manual for Claude Code in this repository. It is loaded at the start of every session. Rules here override any conflicting instruction except an explicit, in-the-moment instruction from a founder that does not break a **Non-negotiable constraint**.

---

## 0. Who is building the backend (read before any task)

Updated 2026-09-23 by Adhi. **Adhi is building the whole backend, both tracks.** Erode Harish has reviewed the outstanding work and confirmed the open points from the 21 and 22 September notice, so that notice is closed; his confirmation was **relayed by Adhi**, not given in a session here, and the points it carried are kept below as a record of what was settled.

What this changes, until a founder says otherwise:

- **Adhi approves and owns every backend area**, the Data track included: `app/db/`, `app/modules/*/models*`, `alembic/`, seed scripts and query performance, as well as the API areas in section 1.
- **The overlap rules in section 1 are dormant, not deleted.** They describe how two people share these files, and they apply again the moment Erode Harish picks work back up. One still binds whoever is working: only one new Alembic migration in flight at a time, so the revision chain cannot fork.
- **One owner is not no process.** The approval gates in section 5, the decision log in section 10, and the definition of done in section 8 all apply unchanged.
- **Reviews.** Section 6 says every merge to `main` goes through a pull request the other founder reviews. While one person is building, say plainly in each pull request and each report that the work has not had a second pair of eyes, rather than letting "reviewed" be assumed.

Recorded as D-051.

<details>
<summary>The closed notice, 21–23 September, kept as a record</summary>


1. By the end of 20 September nothing had been pushed for two Data-track tasks: the `payment_status` table (D-027) and the Creator Passport opt-out column. Five features were blocked behind them, so Adhi's session built them, together with the dispute tables. They are migrations 17–20 (`b5603ae`, `a3e24d4`, `11a9ed6`, `97a9236`). Decisions D-032 to D-036 describe them.
2. Adhi asks you to acknowledge this before starting new backend work. Git only shows what was pushed. If you had work on these that never got pushed, say so; it may still be useful.
3. **Do not write a new migration for `payment_status`, disputes or the Passport column.** Two migrations in flight would fork the chain (section 1).
4. **Your review is what blocks every merge to `main`.** Review **PR #13** (`feature/attention`), starting with migrations 17–20. It contains all of PR #11 and everything since, so Adhi proposes closing #11 and reviewing only #13. Do you agree?
5. After #13, review the PR from `chore/cors-and-docs`, which is stacked on it: the CORS allow-list, 500 errors with every header, and the API docs off in production (D-044, D-045). It touches no Data-track file and adds no migration.
6. **Rate card decision 1** (`docs/PROPOSAL_PASSPORT_RATE_CARD.md`): two new tables and one column. It needs both founders, and the tables are yours to build. What is your decision?
7. After #13 merges, run `pip install -r requirements.txt`: it adds ruff, mypy and pytest-cov (D-037), and CI fails on lint, formatting, types and coverage without them. Shared files Adhi edited on 22 September: `.env.example` (new optional `CORS_ALLOWED_ORIGINS`), `docs/DECISIONS.md` (D-044, D-045) and `docs/standards/security.md`.
8. The full account is in the reports under `docs/reports/` dated 2026-09-21 and 2026-09-22, on those branches.

**Added 23 September.** D-047 locked the technology baseline on 22 September, with your approval relayed by Adhi. Building it has now started.

9. **Branch `chore/tech-baseline` is pushed and its CI is green.** Three rows of the section 4.0 baseline are built: the backend library versions (including the `httpx` → `httpx2` swap); the CI supply chain (both actions pinned to commit SHAs at v7, `persist-credentials: false`, a least-privilege `permissions:` block, and zizmor auditing every run); and Schemathesis fuzzing the API against its own contract. It adds no migration and touches no file in your track. Please review it after PR #13 and the `chore/cors-and-docs` PR.
10. **`requirements.txt` changed again** (shared file, Adhi edited it on 23 September): ten pins moved to current releases, `httpx` was replaced by `httpx2`, and `coverage` and `schemathesis` were added. **Run `pip install -r requirements.txt` before your next session** or CI and your laptop will disagree. Schemathesis found 48 contract failures on its first run; 35 were one bug, now fixed, and the rest are written up in `docs/API_CONTRACT_FINDINGS.md`.
11. **Valkey 9.1.2 or newer, in place of Redis 7** (baseline section 4.2). It is a drop-in for how we use it, the licence is open, and 9.1 is up to 17% faster. It changes `docker-compose.yml` and `.github/workflows/ci.yml`, both of which need both founders. **Do you approve, and do you want to build it or should Adhi?**
12. **PostgreSQL 18, UUIDv7 for new tables, and exact image tags** (baseline section 4.2). We run 16.15 on a floating `pg16` tag. 18 brings asynchronous I/O, native `uuidv7()` and statistics that survive an upgrade. **This is your track and yours to build. When can you take it?**
13. **uv and Python 3.14** (baseline section 4.1). We are on Python 3.12 and plain pip. uv would install and pin both, but it changes the commands in section 4 of this file and the CI workflow, so it needs both founders. Python 3.14 is not installed on Adhi's machine either. **Do you approve, and does moving your local environment to 3.14 cause you any problem?**
14. **Two product decisions Adhi has made that change your track.** (a) **The product is now called Colyv.** The name appears 52 times in 31 tracked files, including `docker-compose.yml`, `.env.example`, `ERROR_TYPE_BASE` in `app/core/errors.py` (a public API contract, and it assumes we own `colyv.in`) and the database name, which means every local database is recreated. Historical reports and `docs/DECISIONS.md` keep the old name, being a record. (b) **English only; Tamil is dropped.** This unpicks several locked D-047 rows, including hybrid Tamil search in Postgres, which is your track, and the Tamil test set that was to choose every AI and embedding model. It also removes what `docs/COMPETITIVE_LANDSCAPE.md` calls our separation from every competitor. **Both need your agreement before anything is renamed or removed, and both need a decision entry.**

State these as facts from git, not as blame.

</details>

---

## 1. Project

NicheConnect TN is a Tamil Nadu-focused brand↔creator marketplace. This repo is the **backend only** (FastAPI).

**Build order (approved):** backend first, to completion. UI/UX design and all frontend work (brand web dashboard, creator mobile app) start only after the backend is complete.

- This repo contains **no frontend code**. Don't create UI, screens, or frontend scaffolding here.
- Design the API around the product's domain (brands, creators, campaigns, applications, deal memos, payment status), not around assumed screens.
- There is no finished dashboard. Any earlier Figma sketches are reference only, not a contract.

**Founders:** two developers. **Since 2026-09-23 Adhi is building the whole backend on his own (section 0, D-051)**, so the split below is how the work divides when both are building, and Adhi approves across all of it meanwhile. When both are building: either founder can approve work inside their own track; anything touching both tracks, the guardrails, or architecture needs both.

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
