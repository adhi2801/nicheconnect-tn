# Daily Engineering Report: 2026-09-23

**Branches:** eight, all pushed  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PRs:** none opened

The day was spent carrying out the technology baseline locked as D-047 on
22 September, which until today was decided and not built. Everything is on
its own branch and **nothing is merged**, which is now the main risk.

## 1. Founder summary

- **The baseline went from 3 of 17 rows built to 6.** Backend libraries, CI
  supply chain and API fuzz testing this morning; Valkey, PostgreSQL 18 and
  Squawk this afternoon. Three decisions recorded: D-048, D-049, D-050.
- **Schemathesis found 48 contract failures on its first run; there is 1
  left**, and that one is correct behaviour rather than a bug. Four fixes,
  each a single root cause. The largest was 35 failures from one line: the
  API document published the `Idempotency-Key` length but never its
  character set, so a client generated from our own document got a 422 on
  keys we never accept.
- **zizmor found two real CI problems nobody had noticed:** `checkout` was
  leaving a usable push token in `.git/config` for every later step to read,
  and the job inherited the repository's default permissions rather than
  read-only. Both fixed; both actions now pinned to commit SHAs.
- **Squawk found a real migration problem** on its first run: migration
  `c3b81e47af20` adds a `CHECK` constraint to the existing `notification`
  table without `NOT VALID`, which takes a full table scan and blocks writes
  while it runs. Harmless now, an outage on a populated table.
- **PostgreSQL 18 did not make us faster, and the plan said it would.**
  Measured against a throwaway 16.15 on the same machine with the same seed,
  the two are indistinguishable. The plan's row is corrected. None of D-049's
  reasons was speed, so the upgrade still stands.
- **Every read endpoint is inside its budget with about twenty times the
  headroom** — p95 between 9.3 ms and 15.8 ms against 300 ms. First time
  these have been measured rather than assumed.
- **Tests: 1,178 passing, coverage 98.06%.** Up from 1,167 this morning.
- **Still blocked on Erode Harish, and it is now the whole critical path.**
  His review blocks every merge, and eight branches are queued behind it. Two
  of his asks have been open since 21 September.

## 2. Work completed

| Task | Status | Evidence |
|---|---|---|
| Backend libraries to D-047 versions | Done | `1669b9d`; 1167 passed on the new pins |
| CI actions SHA-pinned, zizmor added | Done | `2f94964`; zizmor clean, CI green |
| Schemathesis wired in, `Idempotency-Key` fixed | Done | `fa40e4b`; 48 findings to ~14 |
| `phone` / `code` patterns published | Done | `d3da4e6`; 3 findings to 1 |
| 400 documented on every body-taking operation | Done | `d4d5648`; that class cleared |
| Valkey replaces Redis (D-048) | Done | `2c45abc`; verified against a real Valkey 9.1.2 |
| PostgreSQL 18 + pgvector 0.8.6 (D-049) | Done | `14f14ea`; 20 migrations up, down and up again |
| Squawk on added migrations (D-050) | Done | `f9cd363` |
| `Allow` header names every method | Done | `ce5b556`; the class cleared, 8 findings to 1 |
| Performance measured, plan claim corrected | Done | `078c91e`; `docs/PERFORMANCE.md` |
| Backlog refreshed from the code | Done | `976463a` |
| Notice for Erode Harish updated | Done | `5f0852b` |

## 3. Files

### Created
- `docs/API_CONTRACT_FINDINGS.md` — what Schemathesis found, what was fixed, what remains
- `docs/PERFORMANCE.md` — measured budgets, and the 16-versus-18 comparison
- `scripts/lint_new_migrations.py` — runs Squawk over the migrations a branch adds
- `.squawk.toml` — every excluded rule with its reason

### Modified
- `requirements.txt` — ten pins current; `httpx` to `httpx2`; `coverage` and `schemathesis` added
- `.github/workflows/ci.yml` — SHA pins, permissions block, zizmor, Schemathesis, Squawk, Valkey, PostgreSQL 18
- `docker-compose.yml` — Valkey 9.1.2, PostgreSQL 18.6, exact tags, new volume
- `app/core/errors.py` — `Allow` on a 405
- `app/core/openapi.py` — 400 on every operation with a body
- `app/core/idempotent_route.py` — publish the key's pattern
- `app/modules/auth/schemas.py` — publish the phone and OTP patterns
- `app/modules/{auth,notifications}/service.py` — `CursorResult` cast for SQLAlchemy 2.0.54
- `docs/DECISIONS.md` — D-048, D-049, D-050
- `docs/PLATFORM_AND_TECH_PLAN.md` — six rows rescored; the speed claim corrected
- `docs/PRODUCT_BACKLOG.md` — sections 2 to 5 rebuilt from the code

### Deleted
None.

## 4. API changes

No endpoint added, removed or changed in behaviour. Three documentation
corrections, all of which change `docs/api/openapi.json`:

- `Idempotency-Key` now publishes its `pattern` on all 35 operations
- `phone` and `code` publish theirs
- 400 is documented on all 22 operations that take a body

A 405 now returns a complete `Allow` header. That is a behaviour change, but
only to a header that was previously wrong.

## 5. Database changes

No migration was written. PostgreSQL moved from 16.15 to 18.6, and the store
behind rate limits from Redis 7.4.8 to Valkey 9.1.2. **Every developer
recreates their local database:** `docker compose up -d`, then `alembic
upgrade head`. A 16 data directory cannot be read by 18. The old volume is
left in place, so reverting is only reverting the file.

## 6. Testing

- **1,178 passed, coverage 98.06%**, against PostgreSQL 18.6 and Valkey 9.1.2.
- All 20 migrations apply, downgrade to base and reapply cleanly on 18.
- `mypy` clean on 96 files, `ruff check` and `ruff format` clean, `zizmor` clean.
- Schemathesis: 6,829 generated cases with no 5xx anywhere, which is what CI
  gates on.
- **Found today: five tests skip unless the database is seeded**
  (`tests/modules/payment_status/test_payment_concurrency.py:72`). CI has no
  seed step, so **the payment concurrency tests have never run in CI.** See
  technical debt.

## 7. Commits pushed

| Branch | Commits |
|---|---|
| `chore/tech-baseline` | `1669b9d`, `2f94964`, `fa40e4b` |
| `docs/notice-erode-baseline` | `5f0852b` |
| `fix/contract-field-patterns` | `d3da4e6` |
| `fix/document-status-codes` | `d4d5648` |
| `chore/valkey` | `2c45abc` |
| `chore/postgres-18` | `14f14ea`, `f9cd363` |
| `fix/allow-header` | `ce5b556` |
| `docs/performance-baseline` | `078c91e` |
| `docs/backlog-refresh` | `976463a` |

CI green on all of them that had finished at the time of writing.

## 8. Decisions approved today

- **D-048** — Valkey 9.1.2 replaces Redis for the cache and rate limits.
- **D-049** — PostgreSQL 18 with pgvector 0.8.6, on exact image tags.
- **D-050** — Squawk lints the migrations a branch adds, not the whole chain.

All three were approved by Adhi in session, with **Erode Harish's approval
relayed by Adhi** ("harish has confirm everything"), the same way D-047 was
recorded. **His own confirmation of the section 0 notice is still
outstanding** and should be recorded on the day he gives it.

## 9. Dependencies

Added: `schemathesis==4.27.5`, `coverage==7.16.1`. Replaced: `httpx` with
`httpx2==2.13.0`. Ten existing pins moved to current releases. CI-only and
deliberately not in `requirements.txt`: `zizmor==1.30.1`,
`squawk-cli==2.65.0`, matching how `pip-audit` is handled.

Not taken: Starlette 1.7.0 and httpx2 2.13.1, both released the same day.
1.7.0 is a feature release, not a security fix, and it drops AnyIO 3 and
changes WebSocket disconnect behaviour. D-047 wants an upgrade proven on our
tests first.

## 10. Bugs found

1. **`Idempotency-Key` under-documented** — 35 contract failures. Fixed.
2. **`Allow` incomplete on a 405** — fixed, including the subtler half: a
   static path matches its parameterised sibling's pattern, so a first attempt
   advertised a `PATCH` the path cannot serve.
3. **400 undocumented** on every operation taking a body. Fixed.
4. **`checkout` persisted credentials** into `.git/config`. Fixed.
5. **CI ran with the repository's default permissions.** Fixed.
6. **Migration `c3b81e47af20` adds a `CHECK` without `NOT VALID`.** Not
   fixed: it is already applied, and changing it is the Data track's call.

## 11. Technical debt

- **Payment concurrency tests never run in CI**, because CI does not seed.
  Either add a seed step or make those tests build their own fixtures.
- **Writes are unmeasured.** The 500 ms budget has never been checked.
- **No load test**, so every number is one client, sequentially.
- **`require-lock-timeout` and `require-statement-timeout` are off in
  Squawk.** They are the rules worth having. Turning them on changes how
  migrations are written, which is Erode Harish's decision; `.squawk.toml`
  says how.
- **47 pre-existing Squawk findings** on the migrations already merged, 34 of
  them `VARCHAR(n)` where `TEXT` with a `CHECK` is wanted. One schema-wide
  decision, not a per-branch one.
- **`CLAUDE.md` section 4 still says "Redis"** in the compose comment. Left
  alone because that file is shared and a branch holds an edit to it.

## 12. Blockers

1. **Erode Harish's review blocks all eight branches.** Nothing reaches
   `main` without it, and the queue is now nine items long.
2. **Python 3.14 and uv** cannot proceed: 3.14 is not installed on this
   machine, and uv changes `CLAUDE.md` section 4 and CI, so it needs both
   founders.
3. **No notification provider**, so nobody can log in off a developer laptop.
4. **No job runner**, so C5 and E1 cannot start.
5. **No in-app account deletion**, which neither app store will accept.
6. **DPDP consent-manager rules land 13 November 2026**, seven weeks out.

## 13. Health

| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 1,178 tests, 98.06% coverage, strict types, lint clean |
| Database | 🟢 | On 18.6; migrations apply, undo and redo; linted for locks from now on |
| APIs | 🟢 | Contract now matches what the API really answers, proved by fuzzing |
| Tests & CI | 🟡 | Green everywhere, but concurrency tests never run in CI and writes are unmeasured |
| Infrastructure | 🔴 | No hosting, backups, job runner or notification provider |
| Process | 🔴 | Eight unmerged branches, all waiting on one reviewer |

## 14. Next recommended tasks

1. **Merge the eight branches, in order.** They stack through
   `docs/api/openapi.json`, `ci.yml`, `errors.py` and the plan:
   `chore/tech-baseline` → `fix/contract-field-patterns` →
   `fix/document-status-codes` → `chore/valkey` → `chore/postgres-18` →
   `fix/allow-header` → `docs/performance-baseline` → `docs/backlog-refresh`.
   `docs/notice-erode-baseline` is independent and should go first, because it
   is what carries the message.
2. **Reach Erode Harish directly**, rather than waiting for the notice to
   fire in his next session.
3. **Choose the notification provider.** It is the single most expensive open
   decision: it blocks E1, C5 and real logins.
4. **Decide on Python 3.14 and uv**, which unblocks the last movable baseline
   row.

_Not started automatically. Awaiting founder approval._

## 15. Handoff

- **Pick up from:** `docs/backlog-refresh`, which sits on top of the whole
  stack. Every branch is pushed; no PR is open.
- **Open questions:** merge order and who opens the PRs; Python 3.14 and uv;
  the two Squawk timeout rules; whether Colyv and English-only proceed, both
  of which are recorded nowhere but the notice branch and have no decision
  entry.
- **Watch out for:**
  - **Recreate your local database.** PostgreSQL 18 cannot read a 16 data
    directory. `docker compose up -d`, then `alembic upgrade head`.
  - **The 18 image mounts at `/var/lib/postgresql`, not
    `/var/lib/postgresql/data`.** Mounted the old way it refuses to start.
  - `pip install -r requirements.txt` before anything: `httpx` is gone and
    Schemathesis is new.
  - On Windows, set `PYTHONIOENCODING=utf-8` before running Schemathesis, or
    its output cannot be printed.
  - On Adhi's laptop, bare `python` points at another project's venv. Use
    `venv\Scripts\python.exe`.
