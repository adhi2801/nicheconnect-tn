# Daily Engineering Report: 2026-09-21

**Branch:** `feature/creator-passport`  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** [#11](https://github.com/adhi2801/nicheconnect-tn/pull/11) (open)

This report covers two sessions. The first ran late on 20 September until the usage limit cut it off at 00:39. Its nine commits were pushed, but no report covered them. The second is today's, which picked up where that one stopped.

## 1. Founder summary

- **Nothing was lost to the shutdown.** Every commit from last night was already on GitHub. The one unfinished piece, lint and type-check tooling, was still on disk and is now finished.
- **Last night's work, now reported:** the payment record (brand says sent, creator confirms), the brand payment-reliability record, disputes that record both sides without a verdict, the Passport on/off switch, and a fix for double taps corrupting records.
- **The new tools found a real bug in their first minute.** Every list in the app (campaigns, applications, deal memos, notifications) silently skipped rows that shared a timestamp with the last row of a page. A brand could fail to see some applicants. Fixed, with four tests that failed first.
- **New feature: the creator delivery record.** Brands can now see whether a creator delivers, on time, with the ad disclosure confirmed. It mirrors the brand payment record and uses the same rules: silence can't hide a no-show, "new" can't hide overdue work, and nothing is smoothed.
- **CI now enforces quality on every push:** lint, formatting, strict type checking, 80% coverage overall and 90% for every service. Coverage is 97.6%.
- **Tests: 1,009 passing**, up from 959 at the start of today (748 at the last report).
- **Needs you:** three open questions on the delivery record (section 12). The biggest: deals with no agreed date let a creator who never delivers go uncounted.
- **Needs Erode Harish, before he starts new work:** the Data-track tables were built in his absence (section 15). He must review them and must not create a second payment table.

## 2. Work completed

| Task | Status | Evidence |
|---|---|---|
| Payment record table, no status column (D-032) | Tested | `b5603ae`, migration 17; full suite re-run today |
| Payment handshake: mark sent, confirm received | Tested | `d2a3414` |
| "Unconfirmed" when the creator never answers (D-033) | Tested | `a3e24d4`, migration 18 |
| Brand payment-reliability record (D-034) | Tested | `c0cf8de` |
| Dispute record and four endpoints (D-035) | Tested | `11a9ed6`, `3d05617`, migration 19 |
| Passport is opt-in (D-036) | Tested | `97a9236`, migration 20 |
| Double taps no longer corrupt payment or dispute records | Tested | `a325f48`; test fails without the lock |
| Competitive landscape write-up | Implemented | `be8aa90`, `docs/COMPETITIVE_LANDSCAPE.md` |
| Paging skipped rows sharing a timestamp (4 lists) | Tested | `da17d9f`; 4 tests failed before the fix |
| Allow-list checks that survive `python -O` | Tested | `d9ddcd1`; `tests/core/test_literals.py` runs one under `-O` |
| ruff, strict mypy, coverage gates in CI (D-037) | Tested | `4d9be95`; every gate run on the committed tree |
| One-time formatting, ignored by `git blame` | Tested | `3f5dbd3`, `7defcde` |
| Creator delivery record (D-038) | Tested | `7f65d6c`; 36 tests, 3 deliberate rule breaks each caught |
| CI coverage gate no longer depends on thread timing | Tested | `2db4f48`; see section 10 |

## 3. Files

### Created

| File | Purpose |
|---|---|
| `pyproject.toml` | ruff, mypy, pytest and coverage settings, each relaxation with its reason |
| `.git-blame-ignore-revs` | Lets `git blame` skip the formatting commit |
| `app/core/literals.py` | Import-time check that an API Literal matches its database allow-list |
| `app/modules/deal_memo/delivery_record.py` | The creator delivery record: rules (pure) plus two queries |
| `app/modules/deal_memo/delivery_router.py` | `GET /api/v1/creators/{creator_id}/delivery-record` |
| `tests/deal_flow.py` | The shared deal journey used by proof, payment and dispute tests |
| `tests/modules/conftest.py` | Shared `clock` and `client` fixtures (replaces importing them from another test file) |
| `tests/core/test_literals.py` | 5 tests, one under `python -O` |
| `tests/modules/deal_memo/test_delivery_record.py` | 23 rule tests |
| `tests/modules/deal_memo/test_delivery_record_api.py` | 13 endpoint tests |
| Last night: `app/modules/payment_status/*`, `app/modules/disputes/*`, `app/core/clock.py`, migrations 17–20 and their tests | See the commit messages of `b5603ae` to `a325f48` |

### Modified

| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `app/core/pagination.py` | One shared keyset condition, a real SQL row comparison | The Python tuple comparison dropped the id tie-break | Lists no longer skip rows |
| `app/modules/{campaigns,deal_memo,notifications}/service.py` | Use it; typed queries; `db.get_one` where a foreign key guarantees the row | The paging fix, and the type checker | Paging fixed; otherwise none |
| `app/core/taxonomy.py` | Each Literal written once; the tuples read out of it | API types and database lists can no longer drift | None (`alembic check` clean) |
| Six schema and router files | 16 `assert` lines replaced by `ensure_same_values` | Asserts vanish under `-O` | App refuses to start on drift |
| `app/modules/disputes/router.py` | Payment typed properly (was the builtin `any`) | mypy could not check the payment half of any dispute endpoint | None |
| `app/core/health.py`, `app/core/idempotency.py` | Log instead of silently swallowing errors | Silent failures | Warning in logs; no key or id logged |
| `app/main.py` | Registers the delivery router; readiness typed | New endpoint | One new endpoint |
| `requirements.txt` | `ruff`, `mypy`, `pytest-cov` pinned | D-037 | **Everyone re-runs `pip install -r requirements.txt`** |
| `.github/workflows/ci.yml` | Lint, format, type and coverage gates | D-037 | A failure blocks merge |
| `docs/standards/{backend,testing,security}.md` | "Once approved" lines now describe what is enforced | They were stale | None |
| `.gitignore` | `.coverage`, `coverage.json` | Tool output | None |
| 72 files | Reformatted by ruff | One style, enforced | None (formatting only) |
| Data-track files (`app/db/models.py`, three model files, `alembic/env.py`, two scripts) | Import order, `UTC` alias, lint comments, formatting | The lint and format pass | None; no schema change |

### Deleted

None.

## 4. API changes

| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|
| GET | `/api/v1/creators/{creator_id}/delivery-record` | How a creator delivers | Any brand, or the creator themself | 60/min | 36 |
| — | All list endpoints | Paging no longer skips tied rows | Unchanged | Unchanged | 4 new |

Last night's endpoints (payment record, mark paid, confirm, brand reliability, four dispute endpoints, Passport publish and unpublish) are documented in their commit messages. The OpenAPI document was compared byte for byte before and after the tooling commits: identical. After the new feature, the only difference is one new path and one new schema.

## 5. Database changes

| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|
| 17 `f72f456249a6` | `payment_status` table, seven checks | Yes, last night (per commit) | New table |
| 18 `c3b81e47af20` | Two notification types | Yes, last night (per commit) | Wider check |
| 19 `62fca71c7083` | `dispute`, `dispute_event` tables | Yes, last night (per commit) | New tables |
| 20 `386c81bcb3ff` | `creator.passport_published_at` | Yes, last night (per commit) | New column |
| Today | None | n/a | `alembic check` clean after every change |

All four were built by Adhi's session on the Data track. See section 15.

## 6. Testing

- **Commands run:** `venv/Scripts/python.exe -m pytest` (full suite, many times). `ruff check .`, `ruff format --check .`, `mypy`, `pytest --cov` and the per-service floor script, run on each commit's own files, extracted with `git archive`. `pip-audit --requirement requirements.txt --strict`. `alembic check`.
- **Result:** 1,009 passed · 0 failed · 0 skipped. Coverage 97.61% overall; lowest service 94.2%.
- **Measured:** delivery record p95 12.3 ms locally at 50 deals (budget 300 ms).
- **New tests:** 4 same-timestamp paging tests; 5 allow-list guard tests; 23 delivery-record rule tests; 13 delivery-record endpoint tests; deterministic dispute race; dispute not-found; both sides export the same dispute timeline; two paid-date guards.
- **Checked the tests can fail:** paging (failed before the fix), three delivery rules broken on purpose, the dispute race handler removed, the per-service floor raised to 99%. Each failed as it should.

## 7. Commits pushed

```
2db4f48 fix(ci): the coverage floor no longer depends on two threads colliding
7f65d6c feat(deal_memo): a creator's delivery record, the mirror of the brand's
7defcde chore: git blame skips the formatting commit
3f5dbd3 style: format the codebase with ruff, and check it in CI
4d9be95 chore(tooling): ruff, strict mypy and coverage gates in CI (D-037)
d9ddcd1 fix(api): allow-list checks that survive python -O
da17d9f fix(api): list pages no longer skip rows that share a timestamp
--- pushed last night, first reported here ---
be8aa90 docs: competitive landscape, and what it changes about our position
a325f48 fix(payment_status,disputes): two taps at once no longer corrupt the record
97a9236 feat(auth): nobody is on the public Passport until they choose to be
3d05617 feat(disputes): four endpoints, none of which decides who was right
11a9ed6 feat(disputes): a dated record of what both sides said, and no verdict
c0cf8de feat(payment_status): a brand's payment record that silence cannot launder
a3e24d4 feat(payment_status): state the creator's silence rather than assume consent
d2a3414 feat(payment_status): the payment handshake, and a day that starts in India
b5603ae feat(payment_status): the record of a payment, with no status column
```

## 8. Decisions approved today

| ID | Decision | Approved by | Impact |
|---|---|---|---|
| D-032 | Payment table with no status column | Adhi (last night) | State is worked out from dates, never stale |
| D-033 | "Unconfirmed" when the creator never answers | Adhi (last night) | Nobody's silence is turned into consent |
| D-034 | Brand payment record | Adhi (last night) | Silence cannot launder it |
| D-035 | Disputes record, never judge | Adhi (last night) | No verdicts anywhere |
| D-036 | Passport is opt-in | Adhi (last night) | Passport is deployable |
| D-037 | ruff, strict mypy, coverage in CI | Adhi | New gates; three dev packages |
| D-038 | Creator delivery record | Adhi (the feature); three points open | New endpoint; see section 12 |

## 9. Dependencies

| Package | Version | Reason | Approval ref |
|---|---|---|---|
| ruff | 0.16.8 | Lint and format | D-037 |
| mypy | 2.3.1 | Strict type checking | D-037 |
| pytest-cov | 7.1.0 | Coverage floors | D-037 |

`pip-audit`: no known vulnerabilities with these added.

## 10. Bugs found

| Severity | Description | Status |
|---|---|---|
| High | Every list endpoint skipped rows sharing a timestamp with a page's last row (Python tuple comparison instead of SQL). Brands could miss applicants; users could miss notifications | Fixed `da17d9f` |
| Medium | 16 allow-list checks were `assert`s and would vanish under `python -O`, turning a drift into a 500 | Fixed `d9ddcd1` |
| Medium | The per-service coverage gate passed or failed on thread timing (a race-only branch); CI failed on GitHub while passing locally | Fixed `2db4f48` |
| Medium | Two taps at once could record two payments or two disputes (last night) | Fixed `a325f48` |
| Low | Dispute endpoints typed the payment as the builtin `any`, so it was never type-checked | Fixed `4d9be95` |
| Low | A readiness probe and the idempotency store swallowed errors silently | Fixed `4d9be95` |
| Low | Dispute not-found and dispute export had no tests | Fixed `2db4f48` |
| Low | Yesterday's automatic lint fix deleted an explanatory comment | Restored `4d9be95` |

## 11. Technical debt

| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| Undated deals can hide a no-show on the delivery record | `content_due_on` is optional | A creator who never delivers an undated deal is not counted | Founder decision: require a date on paid memos, or a default window (D-038 a) |
| `coverage` is not pinned | pytest-cov pulls it in | Local and CI can differ slightly in branch counting | Pin `coverage==7.16.1` (needs approval: a new direct pin) |
| Two mypy options relaxed | SQLAlchemy and FastAPI decorators | Some `Any` can pass unchecked | Tighten file by file; listed in `pyproject.toml` |
| Takedowns not on the delivery record | Nothing writes `content_removed_on` until the link-check job exists | None today | Add once the job runner is decided |
| Test helpers still repeated in several test files | Consolidated only where it caused lint errors | Drift between copies | Move the rest into `tests/deal_flow.py` gradually |
| No CORS allow-list; `/docs` CSP allows inline scripts | Carried from 20 Sep | As before | As before |

## 12. Blockers

| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| Review of migrations 17–20 and D-032 to D-036 | Data-track work landed without its owner | Review on PR #11, and the acknowledgement in section 15 | Erode Harish |
| Undated deals (D-038 a) | Delivery record has a hiding place | A decision | Both founders |
| Should the brand and creator records ever be public? (D-034 point 5, D-038 b) | Both stay behind a login | A decision | Both founders |
| DPDP: keeping and contesting a record about a person (D-038 c) | Delivery record retention | The validation pack | Both founders |
| Media storage, job runner, who the pilot serves | Carried from 20 Sep | Decisions | Both founders |

## 13. Health

| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 1,009 tests, strict types, one error shape, 61 operations |
| Database | 🟡 | 20 migrations rebuild cleanly, but 4 are awaiting their track owner's review |
| APIs | 🟢 | Contract verified unchanged by the tooling; one new endpoint |
| Tests & CI | 🟢 | 1,009 pass locally; GitHub Actions green on `2db4f48` ([run](https://github.com/adhi2801/nicheconnect-tn/actions/runs/35564271616)) after the thread-timing fix. The PR's own run had not appeared when checked |
| Infrastructure | 🔴 | No hosting, no backups, no job runner. Nothing deployed |

## 14. Next recommended tasks

1. **Erode Harish reviews PR #11's Data-track work**: four migrations landed without their owner, and a second payment table would fork the migration chain.
2. **Decide D-038 point (a), undated deals**: it is the one hole in the delivery record, and the fix is small once decided.
3. **Rate cards on the Creator Passport**: next on the value list in `docs/COMPETITIVE_LANDSCAPE.md`.

_Not started automatically. Awaiting founder approval._

## 15. Handoff

- **Pick up from:** `feature/creator-passport` at the report commit after `2db4f48`, pushed. PR #11 is open and not merged.
- **Pending:** nothing uncommitted.
- **For Erode Harish, please read first.** By the end of 20 September nothing had been pushed for the Data-track tasks: the `payment_status` table (D-027) and the Passport opt-out column. Five features were blocked behind them, so Adhi's session built them, together with the dispute tables: `b5603ae`, `a3e24d4`, `11a9ed6` and `97a9236`, migrations 17 to 20. Adhi has asked that you acknowledge this before starting new backend work. Git only shows what was pushed, so if you had work in progress locally, say so; it may still be useful. Before writing any migration: review those four on PR #11, and **do not create another `payment_status` migration**, because two in flight would fork the chain (CLAUDE.md section 1).
- **Open questions:** D-038 (a), (b), (c) in section 12.
- **Watch out for:**
  - `requirements.txt` changed again. Re-install, or `ruff` and `mypy` will not be found.
  - CI now fails on lint, formatting, types and coverage. Run `ruff format .`, then `ruff check .`, `mypy` and `pytest --cov` before pushing.
  - To make `git blame` skip the formatting commit locally: `git config blame.ignoreRevsFile .git-blame-ignore-revs`.
  - On Adhi's laptop, bare `python` points at another project's venv. Use `venv\Scripts\python.exe`.
- **First command to run:** `pip install -r requirements.txt`

---

## Update: afternoon, 2026-09-21

Work after the wrap-up above, on three branches, each built on the one before: PR #11 (`feature/creator-passport`) → `feature/retry-safety` → `feature/application-feedback`. All pushed; GitHub Actions green on every tip.

### Work completed

| Task | Status | Evidence |
|---|---|---|
| A scored deal needs an agreed date before it is sent, and the date cannot be past (D-039, closes D-038 a) | Tested | `6987c53` on PR #11; 9 tests, each check removed once to prove its tests fail |
| Every write outside login is safe to retry (D-040) | Tested | `f047a6e`; 11 tests failed before the change with the false 409s and duplicates, pass after; a test fails if any new write lacks the header |
| Why a creator's applications are not turning into deals, `GET /api/v1/applications/me/feedback` (C4, D-041) | Tested | `0668508`, `c623533`; 22 tests, 4 rules broken on purpose and caught |
| Performance of every Phase B endpoint measured on seeded data | Tested | Table below |
| Notice for Erode Harish at the top of `CLAUDE.md` | Implemented | `docs/notice-for-erode` branch, `e1d794d`; takes effect once merged to `main` |

### Measured performance

Seeded dev database (150 campaigns, 786 applications, 200 creators) plus one brand with 60 complete deals, built inside a transaction that was rolled back afterwards: nothing was left behind. Reads 100 runs each; writes one per deal.

| Endpoint | p95 ms | Budget |
|---|---|---|
| Phase A list endpoints (existing script) | ≤ 14.2 | 300 |
| `GET /deal-memos/mine`, memo, proof, payment, dispute | ≤ 10.5 | 300 |
| `GET /brands/{id}/reliability` (60 deals) | 12.9 | 300 |
| `GET /creators/{id}/delivery-record` | 10.0 | 300 |
| `GET /applications/me/feedback` (busiest seeded creator) | 23.4 | 300 |
| `GET /me/export` (brand with 60 deals) | 83.2 | 300 |
| Every Phase B write (create, send, accept, proof, approve, mark paid, confirm, dispute) | ≤ 23.8 | 500 |

Worst p95 is 28% of its budget. **Caveat:** inside the test transaction a commit releases a savepoint instead of writing to disk, so write figures are a lower bound. The margin is wide enough that this does not change the verdict.

### Decisions approved

| ID | Decision | Approved by |
|---|---|---|
| D-039 | Paid, commission and local-business memos need an agreed date to be sent; the date cannot be past at send or accept | Adhi |
| D-040 | Idempotency-Key on every `POST` and `PATCH` outside `/api/v1/auth/`; login excluded pending its own decision | Adhi |
| D-041 | Application feedback: most common reason only from three rejections and never on a tie; profile facts, not gaps | Adhi |

### Testing

- **Result:** 1,051 passed · 0 failed · 0 skipped. Coverage 97.65%, every service above 90%.
- **Contract:** checked operation by operation for each branch. D-040 changed 24 operations, each only by the added header and its 503. C4 added one path and one schema. Nothing else changed.

### Still open, for founders

- Whether the brand and creator records should ever be public (D-034 point 5, D-038 b).
- DPDP: keeping and contesting a record about a person (D-038 c), for the validation pack.
- Whether login steps should be retry-safe (excluded from D-040).
- Audience size on creator profiles, which fair-rate guidance (C3) needs: a creator column, so Erode Harish's track.
- Merging `docs/notice-for-erode`, so Erode Harish's sessions show him the notice.
