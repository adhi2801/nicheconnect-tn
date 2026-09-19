# Daily Engineering Report: 2026-09-19

**Branch:** `feature/phase-b-and-hardening`  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** not opened — [open it](https://github.com/adhi2801/nicheconnect-tn/compare/feature/phase-b-and-hardening?expand=1)

## 1. Founder summary
- **Phase A was closed properly:** seed data, and performance **measured** at 20,000 campaigns — every list endpoint p95 between 12 and 45 ms against a 300 ms budget.
- **The deal flow now runs end to end in the backend:** a brand drafts a memo for an accepted application, sends it, the creator accepts or asks for a change, the creator submits proof, and the brand approves it — or the clock does.
- **In-app notifications** record every one of those events for the other side.
- **Deployment blockers cleared:** correct client IP behind a proxy, `/readyz` that really checks, rate limits ready for Redis, and CI that proves migrations undo as well as apply.
- **Two security gaps closed:** per-phone guess limit, and a proxy fix that stopped one attacker being able to lock out every user.
- **Policy decided and recorded (D-024 to D-030):** proof, the 7-day approval window, cancellation, payment timing and methods, disputes, reminders — with the improvements from Erode's feedback and three changes I argued for.
- **Tests: 599**, up from 464 this morning. 16 migrations rebuild an empty database cleanly.
- **Erode's D-016 approval recorded**, and `campaigns` added to the module list in `CLAUDE.md`.

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| Seed script with Tamil Nadu sample data | Tested | `46d3f3c`, 20,000 campaigns in 41s |
| Measured p95 per list endpoint, with query plans | Tested | `46d3f3c`, table in section 6 |
| Query-count guards against N+1 | Tested | `46d3f3c`, `test_list_query_counts.py` |
| Six tests that assumed an empty database | Fixed | `46d3f3c` |
| Dropped two unused indexes (D-017) | Tested | `6e5b907`, re-measured after |
| Per-phone guess limit (D-018) | Tested | `5359209`, 4 tests |
| CI checks migrations undo and redo (D-019) | Tested | `a0becf8`, verified locally |
| One source for the database address and refresh lifetime | Tested | `62a1fda` |
| `/readyz` checks database and Redis | Tested | `71f3200`, verified by stopping Redis |
| Proxy-aware client IP (D-020) | Tested | `4b3012f`, 15 tests |
| Rate-limit storage configurable, Redis-ready (D-021) | Tested | `549263c`, 11 tests |
| Blueprint mapping and WhatsApp reduction (D-022) | Implemented (docs) | `00a53d5` |
| In-app notifications (D-023) | Tested | `6a5bc10`, 18 tests |
| Phase B policy (D-024 to D-030) | Recorded | `d56d113` |
| Deal memo table | Tested | `d56d113`, 38 tests |
| Memo rules and notifications | Tested | `955d0ce` |
| Memo endpoints | Tested | `035ce5a`, 29 tests |
| Proof of work | Tested | `1bb8759`, 24 tests |
| Erode's D-016 approval, `campaigns` in CLAUDE.md | Done | `6d38fd5` |

## 3. Files
### Created
| File | Purpose |
|---|---|
| `scripts/seed_dev_data.py`, `scripts/measure_performance.py` | Sample data and measured performance, local only |
| `app/core/health.py` | Readiness checks with short timeouts |
| `app/core/client_ip.py` | The caller's real address behind a trusted proxy |
| `app/modules/notifications/{models,service,schemas,router,exceptions}.py` | In-app notifications |
| `app/modules/deal_memo/{models,service,schemas,router,dependencies,exceptions}.py` | The deal memo |
| `app/modules/deal_memo/{proof_models,proof_service,proof_router}.py` | Proof of work |
| 6 migrations | notification, deal_memo, memo notification types, deliverable_proof, proof notification types, drop GIN indexes |
| `docs/FRONTEND_BLUEPRINT_MAPPING.md` | All 40 blueprint screens mapped to the backend |
| 7 test files | Query counts, health, client IP, rate-limit storage, notifications, memo (model + API), proof |
### Modified
| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `app/core/config.py` | `trusted_proxies`, `rate_limit_storage_uri` | D-020, D-021 | Same locally; correct in deployment |
| `app/core/rate_limit.py` | Keyed by the real client, storage from settings | D-020, D-021 | Limits work behind a proxy and across processes |
| `app/main.py` | Real readiness checks; four routers | — | 30 → 44 endpoints |
| `app/modules/auth/service.py` | Per-phone guess limit | D-018 | 15 possible guesses per 10 min → 10 |
| `app/modules/auth/tokens.py` | Machine-clock checks off | Bug fix | Clock skew no longer logs people out |
| `app/modules/campaigns/models.py`, `service.py` | GIN indexes dropped; notifications on application events | D-017, D-023 | Faster writes; both sides told what happened |
| `.github/workflows/ci.yml` | Downgrade round trip, `alembic check`, Redis service | D-019, D-021 | A broken downgrade now fails the build |
| `alembic/env.py`, `app/db/session.py` | Settings as the single source | backend.md section 8 | None |
| `CLAUDE.md` | `campaigns` in the module list | D-016 | Governance |
| `docs/DECISIONS.md` | D-017 to D-030 | Decision log | — |
| `tests/factories.py`, 6 test files | Unique emails; tests no longer assume an empty database | testing.md section 3 | Suite passes with or without sample data |
### Deleted
| File | Reason |
|---|---|
| `tests/test_health.py` | Replaced by `tests/core/test_health.py`, which tests real checks |

## 4. API changes
14 new endpoints, all rate limited, documented, with ownership checks.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/v1/notifications` | My notifications, paged, unread filter | Any |
| GET | `/api/v1/notifications/unread-count` | The badge | Any |
| POST | `/api/v1/notifications/{id}/read`, `/read-all` | Mark read | Owner |
| POST | `/api/v1/deal-memos/for-application/{id}` | Draft a memo | Brand |
| GET | `/api/v1/deal-memos/mine`, `/{id}` | List and read | Both sides |
| PATCH | `/api/v1/deal-memos/{id}` | Change while the brand holds it | Brand |
| POST | `/api/v1/deal-memos/{id}/{send,cancel}` | Brand moves | Brand |
| POST | `/api/v1/deal-memos/{id}/{accept,decline,withdraw,request-change}` | Creator moves | Creator |
| POST | `/api/v1/deal-memos/{id}/proof` | Submit proof | Creator |
| GET | `/api/v1/deal-memos/{id}/proof` | List submissions | Both sides |
| POST | `/api/v1/deal-memos/{id}/proof/{id}/{approve,request-revision}` | Review | Brand |

`/readyz` now returns 503 with the standard error body when a dependency is down.

## 5. Database changes
| Migration | What | Downgrade tested | Impact |
|---|---|---|---|
| `66527a152dfc` | Drops the two unused GIN indexes | Yes | Faster writes; measured no read cost |
| `afd94871a10d` | `notification` table | Yes | New |
| `a41ce4028df6` | `deal_memo` table | Yes | New |
| `304a0b04912a` | Memo notification types | Yes (deletes rows of the new types) | Constraint |
| `29632d604015` | `deliverable_proof` table | Yes | New |
| `7c1f2a9be4d3` | Proof notification types | Yes (same) | Constraint |

`downgrade base` → `upgrade head` rebuilds all 16; `alembic check` reports no drift.

## 6. Testing
- **Commands run:** `pytest` (many times, final run in wrap-up), per-file runs, `alembic downgrade base`/`upgrade head`/`check`, `scripts/seed_dev_data.py`, `scripts/measure_performance.py --explain`
- **Result:** 599 passed · 0 failed · 0 skipped
- **Measured performance** (20,000 campaigns, 40,000 applications, 2,000 creators; budget 300 ms):

| Endpoint | p50 | p95 |
|---|---|---|
| `GET /campaigns/discover` | 9.5 ms | 25.3 ms |
| `GET /campaigns/discover?city&niche` | 11.6 ms | 13.9 ms |
| `GET /campaigns` (mine) | 11.6 ms | 12.8 ms |
| `GET /campaigns/{id}` | 8.7 ms | 12.5 ms |
| `GET /campaigns/{id}/applications` | 13.0 ms | 45.0 ms |
| `GET /applications/me` | 25.3 ms | 35.0 ms |
| `GET /auth/me` | 11.0 ms | 13.5 ms |

- **New tests (135):** query counts 4, health 8, client IP 15, rate-limit storage 11, notifications 18, memo model 38, memo API 29, proof API 24, per-phone limit 4, token clock skew 1, plus adjustments
- **Checks that the tests catch real faults:** removing the GIN indexes was re-measured; the duplicate-application test caught a regression from a flush I added; the constraint migration broke the database and 380 tests until the name was fixed.
- **Not verified:** CI results for this push.

## 7. Commits pushed
```
1bb8759 feat(deal_memo): proof of work, reviewed or approved by the clock
035ce5a feat(deal_memo): memo endpoints, draft to accepted or cancelled
955d0ce feat(deal_memo): memo rules and memo notifications
6d38fd5 docs: record Erode's approval of D-016 and add campaigns to the module list
d56d113 feat(deal_memo): deal memo table, and the Phase B policy decisions
6a5bc10 feat(notifications): in-app notifications from application events (D-023)
00a53d5 docs: map the Frontend Blueprint to the backend, cut WhatsApp scope
549263c feat(core): configurable rate-limit storage, Redis-ready (D-021)
4b3012f feat(core): trust X-Forwarded-For only from configured proxies (D-020)
71f3200 feat(core): /readyz checks the database and Redis
62a1fda refactor: one source for the database address and refresh lifetime
a0becf8 ci: check that migrations undo and redo (D-019)
5359209 fix(auth): cap wrong code guesses per phone (D-018)
6e5b907 perf(campaigns): drop the unused GIN indexes (D-017)
46d3f3c test(perf): seed script, measured p95 and query-count guards
```
(plus this report's commit)

## 8. Decisions approved today
| ID | Decision | Approved by |
|---|---|---|
| D-017 | Drop the unused GIN indexes | Adhi |
| D-018 | Per-phone limit on wrong code guesses | Adhi |
| D-019 | CI checks migrations undo and redo | Adhi |
| D-020 | Client IP from a trusted `X-Forwarded-For` | Adhi |
| D-021 | Rate-limit storage configurable, Redis-ready | Adhi |
| D-022 | WhatsApp is alerts plus two one-tap replies | Adhi |
| D-023 | In-app notifications stored as type plus details | Adhi |
| D-024 to D-030 | Phase B policy: proof, approval window, cancellation, payment, disputes, reminders, open points | Adhi |
| D-016 | Campaigns module | **Adhi and Erode Harish** (confirmed today) |

## 9. Dependencies
None added or removed.

## 10. Bugs found
| Severity | Description | Status |
|---|---|---|
| High | PyJWT refused tokens issued slightly ahead of the machine clock, so clock skew between servers would log people out | Fixed; our injectable clock decides |
| Medium | A flush added for notifications moved where duplicate applications fail, breaking the "already applied" message | Fixed; caught by an existing test |
| Medium | My constraint migration let the naming convention prefix the name twice, half-migrating the database and failing 380 tests | Fixed; both drop and create now mark the name final |
| Low | Six tests assumed an empty database | Fixed; they check only their own rows |

## 11. Technical debt
| Item | Why | Risk | Plan |
|---|---|---|---|
| Proof has no file attachments | Waiting on the media storage decision | Medium: D-024 is only half delivered | Decide storage, then screenshots and recordings |
| No scheduled jobs | Job runner undecided | Medium: reminders (day-3, payment due) do not exist | Decide the runner; auto-approval already works without one |
| Link re-checks not running | Same | Medium: "it stayed up" is unproven | A scheduled check writes `content_removed_on` |
| Cities are free text | No agreed list | Low | Decide a Tamil Nadu city list |
| Brand teams unsupported | One account, one profile (D-011, D-014) | Medium: the blueprint assumes teams | Settle who the pilot serves (D-030) |
| Matching is MVP in the blueprint, Phase D here | Sequencing conflict | Medium | Founder decision |
| Reliability record and disputes not built | Phase B continues | Medium | Next, after payment |
| No backups or restore test | Needs hosting | High before launch | After the hosting decision |

## 12. Blockers
| Blocker | Impact | What is needed | From whom |
|---|---|---|---|
| Media storage decision | Proof attachments, and the blueprint's upload screens | Bucket or database, size limits, resumable uploads | Both founders |
| Job runner decision | Reminders, link re-checks, retention jobs | RQ, ARQ or Celery, and a worker process | Both founders |
| Hosting decision | Backups, Redis in production, proxy settings | Platform choice | Both founders |
| Who the pilot serves (D-030) | The account model: one-person shops or brand teams | Decide before team-account work | Both founders |
| Validation pack | ASCI, DPDP retention, GST and TDS, the dispute posture | Answers from qualified sources | Both founders |

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 44 endpoints; the deal flow runs end to end |
| Database | 🟢 | 16 migrations; round trip and `alembic check` clean |
| APIs | 🟢 | Rate limited, documented, ownership checked, measured |
| Tests & CI | 🟡 | 599 pass locally; CI for this push not verified |
| Infrastructure | 🟡 | Ready for a proxy and Redis, but hosting, backups and jobs are undecided |

## 14. Next recommended tasks
1. **Open the PR** for this branch and have Erode review and merge it.
2. **Payment handshake (D-027):** brand marks paid by UPI, bank or cash; creator confirms; late at 7 days, unpaid at 21.
3. **Reliability record (D-027)** from those events, shown only after 3 completed deals.
4. **Disputes (D-028)** with the evidence timeline.
5. **Media storage decision**, then proof attachments.
6. **Job runner decision**, then reminders and link re-checks.

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** `feature/phase-b-and-hardening` at the report commit (code at `1bb8759`)
- **Pending:** this PR; the payment handshake; four decisions (media, jobs, hosting, who the pilot serves).
- **Open questions:** the four above, plus the validation pack.
- **Watch out for:**
  - After pulling, run `alembic upgrade head`: six new migrations.
  - `.env` gains nothing required, but `TRUSTED_PROXIES` and `RATE_LIMIT_STORAGE_URI` exist now and matter in deployment.
  - A changed `CHECK` constraint needs a hand-written migration, with `op.f()` on both the drop and the create.
  - Sample data and tests share one database: the tests are written to cope, and `scripts/seed_dev_data.py --reset` clears it.
- **First command to run:** `git fetch origin`, then `alembic upgrade head`
