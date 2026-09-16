# SETUP_GOVERNANCE.md: one-time setup file

**Instructions for Claude Code**

A founder has approved this setup. Do exactly the following, then stop:

1. Create or overwrite the four files below with **exactly** the content between each pair of `~~~~` fences. Don't change any wording.
   - `CLAUDE.md` (overwrite the existing one)
   - `.claude/commands/wrap-up.md` (create the folders if missing)
   - `.claude/commands/handoff.md`
   - `docs/DECISIONS.md`
2. Create an empty folder `docs/reports/` containing an empty `.gitkeep` file.
3. Delete this file (`SETUP_GOVERNANCE.md`).
4. Run `git status --short` and show the result.
5. Don't commit or push. Tell the founder: "Setup complete. Review the files, replace both `<founder name>` placeholders in docs/DECISIONS.md, then type `wrap up`."

---

## File: `CLAUDE.md`

~~~~markdown
# CLAUDE.md — NicheConnect TN Backend

This file is the operating manual for Claude Code in this repository. It is loaded at the start of every session. Rules here override any conflicting instruction except an explicit, in-the-moment instruction from a founder that does not break a **Non-negotiable constraint**.

---

## 1. Project

NicheConnect TN is a Tamil Nadu-focused brand↔creator marketplace. This repo is the **backend only** (FastAPI).

**Build order (approved):** backend first, to completion. UI/UX design and all frontend work (brand web dashboard, creator mobile app) start only after the backend is complete.

- This repo contains **no frontend code**. Don't create UI, screens, or frontend scaffolding here.
- Design the API around the product's domain (brands, creators, campaigns, applications, deal memos, payment status), not around assumed screens.
- There is no finished dashboard. Any earlier Figma sketches are reference only, not a contract.

**Founders:** the two developers on this repo. Either founder can approve work on their own track; anything touching both tracks, the guardrails, or architecture needs both.

**Tracks**

| Track | Scope |
|---|---|
| Data | Alembic, tables and migrations, pgvector, Redis wiring, matching data |
| API | Rate limiting, CI, auth, endpoints, API docs & contracts |

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
- **Modules:** `app/modules/{auth, matching, deal_memo, payment_status, notifications}`. Inside a module: `router.py` (HTTP) → `service.py` (rules) → `models.py` (DB), plus `schemas.py`.
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

Approved decisions are recorded in `docs/DECISIONS.md` (section 9).

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

## 7. Definition of done

- [ ] Follows sections 2, 3 and 6
- [ ] Tests for success and failure cases, run in this session and passing
- [ ] Public endpoints rate limited
- [ ] Schema changes only via a reviewed migration with a working downgrade
- [ ] No new dependency without a recorded approval
- [ ] Committed on a feature branch and pushed
- [ ] PR open, CI green, reviewed by the other founder

---

## 8. Commands founders can type

| Founder types | Claude does |
|---|---|
| `wrap up` or `/wrap-up` | End-of-session routine: verify, commit, **push**, write the daily report. Follow `.claude/commands/wrap-up.md` exactly. |
| `handoff` or `/handoff` | Short handover so the other founder can continue immediately. Follow `.claude/commands/handoff.md`. |
| `status` | Five lines max: branch, last commit, uncommitted files, test state, next step. No changes. |
| `decision log` | Show `docs/DECISIONS.md` entries from the last 7 days. |

Reports are built from **evidence** (git history, diffs, test runs from this session, `docs/DECISIONS.md`), never from memory alone. Anything that can't be backed by evidence is marked "not verified".

---

## 9. Decision log

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

## 10. Communication

- Direct, concise, plain English. Explain jargon the first time it's used.
- Surface blockers and risks early; don't bury them.
- When uncertain: present options, explain trade-offs, ask, wait.
~~~~

## File: `.claude/commands/wrap-up.md`

~~~~markdown
---
description: End-of-session routine. Verify the work, commit, push the branch, and write the Daily Engineering Report.
---

# Wrap-up

The founder typing `wrap up` (or `/wrap-up`) **is approval to commit and push the current feature branch**, provided every safety check below passes. Anything outside this routine still needs normal approval.

Work through the phases in order. Never skip one. If a **STOP** condition is hit, stop, explain it in plain English, give the exact fix, and ask how to proceed. Do not work around it.

Developers use Windows PowerShell: run commands one at a time.

---

## Phase 1: Collect evidence

Run and read the output of:

```
git branch --show-current
git status --short
git log --oneline -15
git log --oneline @{u}..HEAD
git diff --stat
git diff --cached --stat
```

If `@{u}` errors, the branch has no upstream yet. Note that and continue.

Also gather:
- Test commands actually run this session, and their results
- `docs/DECISIONS.md` entries added today
- Any migrations under `alembic/versions/` added or changed
- Any change to `requirements.txt`

---

## Phase 2: Safety checks

| Check | How | If it fails |
|---|---|---|
| Not on `main` | branch name | **STOP.** Offer to create `feature/<name>` from the current changes |
| No merge conflicts in progress | `git status` | **STOP** |
| No secrets staged or unstaged | Look for `.env`, `*.pem`, `*.key`, `id_rsa`, lines like `SECRET_KEY=`, `API_KEY=`, `TOKEN=` with real values, and anything under `venv/` | **STOP.** Unstage it and suggest a `.gitignore` entry |
| Restricted vocabulary | Search the changed files for the four banned terms in `CLAUDE.md` section 2 | **STOP.** List the file and line numbers |
| No large or generated files | Files over 5 MB, `__pycache__`, build output | **STOP** |
| Dependencies approved | Every new package in `requirements.txt` has an approval in this session or in `docs/DECISIONS.md` | **STOP.** List the unapproved packages |
| Migrations reviewed | Every new migration was shown to and approved by a founder | **STOP** |

---

## Phase 3: Tests

Run `pytest`.

- **All pass:** continue.
- **Failures:** **STOP.** Show a summary of the failing tests and their likely cause. Ask:
  - A) fix now
  - B) commit to the branch marked work-in-progress, push, and note the failures prominently in the report
  - C) don't commit
- **Can't run** (for example, Docker is off): say so, ask whether to continue, and mark tests "Not run" in the report.

Never report tests as passing unless they ran in this phase or earlier in this session.

---

## Phase 4: Commit

1. Show the list of files to be committed, grouped as new, modified and deleted.
2. Group the changes into logical commits, at most one per concern, using Conventional Commits:
   `feat(scope): …`, `fix(scope): …`, `test(scope): …`, `docs: …`, `chore: …`
   If tests failed and the founder chose B, prefix the subject with `wip:`.
3. Stage files **by name** (`git add path/to/file`), never `git add .` or `git add -A`.
4. Commit. Messages must not contain the restricted vocabulary.

If there is nothing to commit and nothing unpushed, skip to Phase 6 and say so.

---

## Phase 5: Push

1. `git fetch origin`
2. If the remote branch has commits you don't have: **STOP.** Explain, and ask before `git pull` (merge, not rebase).
3. Push:
   - No upstream yet: `git push -u origin <branch>`
   - Otherwise: `git push`
4. Confirm by running `git log --oneline @{u}..HEAD`. It must print nothing.
5. If the push fails (auth, network, rejected): **STOP.** Show the error, explain it in plain English, and give the exact fix. Do not retry with force.
6. Give the PR link: `https://github.com/adhi2801/nicheconnect-tn/compare/<branch>?expand=1`. Never merge it.

---

## Phase 6: Write the Daily Engineering Report

Save it to `docs/reports/YYYY-MM-DD-<branch-name>.md`, then commit it on the same branch (`docs: add engineering report YYYY-MM-DD`) and push again, running the Phase 5 checks.

Also print the **Founder summary** section in the chat.

Use this template. Write every section; put "None" where nothing applies.

```markdown
# Daily Engineering Report: YYYY-MM-DD

**Branch:** `<branch>`  ·  **Author:** <founder>  ·  **Pushed:** Yes / No  ·  **PR:** <link or "not opened">

## 1. Founder summary
<Max 8 bullets, plain English, readable in 2 minutes: what got done, what changed for users or the team, what's blocked, what's next.>

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| <task> | Proposed / Implemented / Tested / Verified | <commit hash, test name> |

## 3. Files
### Created
| File | Purpose |
|---|---|
### Modified
| File | What changed | Why | Behaviour impact |
|---|---|---|---|
### Deleted
| File | Reason | Impact |
|---|---|---|

## 4. API changes
| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|

## 5. Database changes
| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|

## 6. Testing
- **Commands run:** <exact commands>
- **Result:** <n> passed · <n> failed · <n> skipped. If not run, say "Not run" and why.
- **New tests:** <list>

## 7. Commits pushed
<output of `git log --oneline` for commits pushed in this session>

## 8. Decisions approved today
| ID | Decision | Approved by | Impact |
|---|---|---|---|

## 9. Dependencies
| Package | Version | Reason | Approval ref |
|---|---|---|---|

## 10. Bugs found
| Severity | Description | Status |
|---|---|---|

## 11. Technical debt
| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|

## 12. Blockers
| Blocker | Impact | What's needed | From whom |
|---|---|---|---|

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 / 🟡 / 🔴 | |
| Database | 🟢 / 🟡 / 🔴 | |
| APIs | 🟢 / 🟡 / 🔴 | |
| Tests & CI | 🟢 / 🟡 / 🔴 | |
| Infrastructure | 🟢 / 🟡 / 🔴 | |

## 14. Next recommended tasks
1. <highest priority>: why
2. <next>
3. <later>

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** <branch, last commit>
- **Pending:** <unfinished work and state>
- **Open questions:** <for the other founder>
- **Watch out for:** <warnings, assumptions>
- **First command to run:** `<command>`
```

---

## Phase 7: Close

End with exactly these lines in the chat:

```
Wrap-up complete
Branch:   <branch>  (pushed ✓ / not pushed ✗)
Tests:    <n passed / n failed / not run>
Report:   docs/reports/<file>.md
Next:     open PR → <link>   |   or: <blocker to resolve>
```

Do not start new work after wrap-up.
~~~~

## File: `.claude/commands/handoff.md`

~~~~markdown
---
description: Short handover so the other founder can continue this work immediately. Read-only, no commits.
---

# Handoff

Read-only. Don't modify, commit or push anything. If there are uncommitted or unpushed changes, say so at the top and recommend running `wrap up` first.

Collect evidence first:

```
git branch --show-current
git status --short
git log --oneline -10
git log --oneline @{u}..HEAD
```

Also check the latest file in `docs/reports/` and recent entries in `docs/DECISIONS.md`.

Print this in the chat. Keep it under one screen and use plain English.

```markdown
# Handoff: <branch> · YYYY-MM-DD

⚠️ <Only if relevant: "3 files uncommitted / 2 commits not pushed. Run wrap up first.">

**Goal of this branch:** <one line>

**Done**
- <item> (Tested / Implemented / Proposed)

**Not done yet**
- <item>: <current state>

**Open decisions** (need a founder)
- <decision>: options A / B

**Blockers**
- <blocker>: <what unblocks it>

**Watch out for**
- <gotchas, assumptions, fragile areas>

**To continue**
1. `git fetch origin`
2. `git checkout <branch>`
3. `git pull`
4. `docker compose up -d`
5. `pytest`  → expect <n> passed
6. Next task: <specific next step>

**Suggested first prompt for Claude Code**
> I'm continuing branch <branch>. <Done summary>. Next: <task>. Follow CLAUDE.md learning format.
```
~~~~

## File: `docs/DECISIONS.md`

~~~~markdown
# Decision Log

Append-only record of decisions **explicitly approved by a founder**. Recommendations and assumptions don't belong here. Format and rules: `CLAUDE.md` section 9.

Newest entries at the bottom.

---

## D-001: Modular monolith on FastAPI
- Date: 2026-09-14
- Approved by: Founders
- Context: Choosing the backend shape for a two-person team that has to ship a pilot quickly.
- Options considered: A) Modular monolith (one FastAPI app) · B) Microservices
- Chosen: A
- Reason: One deployable app is simpler to build, test and operate; module boundaries keep a later split possible.
- Consequences / follow-ups: New services need both founders' approval.

## D-002: PostgreSQL + pgvector, Redis, Alembic
- Date: 2026-09-14
- Approved by: Founders
- Context: Data store for relational data and similarity matching.
- Options considered: A) Postgres + pgvector · B) Postgres plus a separate vector database
- Chosen: A, with Redis for cache, limits and jobs, and Alembic for migrations
- Reason: One database for relational data and vectors; fewer moving parts.
- Consequences / follow-ups: Every schema change goes through Alembic.

## D-003: slowapi for rate limiting
- Date: 2026-09-16
- Approved by: <founder name>
- Context: Every public endpoint must be rate limited (CLAUDE.md section 2).
- Options considered: A) slowapi · B) Custom middleware · C) Limit at the hosting proxy only
- Chosen: A, with an in-memory store for now and Redis before deploy
- Reason: FastAPI-native, small, well known.
- Consequences / follow-ups: Switch the storage to Redis before running more than one process.

## D-004: Backend first; UI/UX and frontend after the backend is complete
- Date: 2026-09-16
- Approved by: <founder name>
- Context: The earlier plan assumed a finished brand dashboard prototype to wire up. There isn't one.
- Options considered: A) Build backend and frontend in parallel · B) Complete the backend first, then UI/UX design, web dashboard and mobile app
- Chosen: B
- Reason: A stable, tested API lets the UI be designed against real data and contracts, with no rework.
- Consequences / follow-ups: No frontend code in this repo. The roadmap's dashboard integration moves to after backend completion.
~~~~
