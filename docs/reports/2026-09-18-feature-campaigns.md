# Daily Engineering Report: 2026-09-18

**Branch:** `feature/campaigns`  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** not opened — [open it](https://github.com/adhi2801/nicheconnect-tn/compare/feature/campaigns?expand=1)

## 1. Founder summary
- **The marketplace core works end to end:** a brand creates a profile, posts a campaign, publishes it; a creator creates a profile, finds it, applies; the brand shortlists, accepts or rejects with a reason; the creator can withdraw.
- **Login is complete:** refresh with theft detection, logout, log out of all devices, and a "who am I" check that every protected endpoint uses.
- **The database now refuses impossible data**: a profile can only belong to an account of its own role, one account cannot own both profiles, and an account's role cannot change while a profile exists (the automated review's finding on PR #5).
- **Two planning documents** were added: the backend backlog mapped from the playbook, and an analysis of what the playbook does not cover (revenue, seeding, metrics, policy, trust and safety, operations, privacy, reliability, security, AI evaluation, language, life after v2).
- **Tests: 449 passing**, up from 232 yesterday. Three real bugs were found and fixed on the way (below).
- **Waiting on Erode:** the new `campaigns` module changes the approved architecture (D-016), and decisions D-004 to D-016 have one founder's approval.
- **Next:** deal memos and the payment handshake (Phase B), which is where the trust features live.

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| Profile–role database rule (D-014) | Tested | `fe07f52`, `tests/modules/auth/test_profile_role_link.py` |
| Refresh, logout, log out of all devices | Tested | `7712292`, `test_refresh_service.py`, `test_refresh_api.py` |
| Current-account check and role gates | Tested | `7712292`, `test_current_account_api.py` |
| `docs/PRODUCT_BACKLOG.md` | Implemented (docs) | `7712292` |
| `docs/PLAYBOOK_GAPS.md` | Implemented (docs) | `eeab923` |
| Campaign table (D-015, D-016) | Tested | `120c879`, `test_campaign_model.py` |
| Campaign endpoints | Tested | `7a5859f`, `test_campaign_api.py` |
| Brand and creator profile endpoints | Tested | `1b4037e`, `test_profile_api.py` |
| Application table and endpoints | Tested | `1e5243b`, `test_application_api.py` |
| Shared cursor pagination | Tested | `7a5859f`, exercised by three list endpoints |
| Migration round trip, all 10 | Tested | `alembic downgrade base` → `upgrade head`; `alembic check` clean |

## 3. Files
### Created
| File | Purpose |
|---|---|
| `app/core/pagination.py` | One cursor-pagination style for every list endpoint |
| `app/core/taxonomy.py` | Shared niche and language lists |
| `app/modules/campaigns/` (`models.py`, `schemas.py`, `service.py`, `router.py`, `application_router.py`, `dependencies.py`, `exceptions.py`) | Campaigns and applications (D-016) |
| `app/modules/auth/profiles.py`, `profile_router.py` | Brand and creator profile rules and endpoints |
| `alembic/versions/25932ee8f40b_…` | Ties each profile to its account's role |
| `alembic/versions/b9f74ec5b426_…` | Campaign table |
| `alembic/versions/ee268d5e08eb_…` | Application table |
| `docs/PRODUCT_BACKLOG.md`, `docs/PLAYBOOK_GAPS.md` | Planning |
| 6 test files | Profile–role, refresh, current account, campaigns, applications, profiles |
### Modified
| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `app/modules/auth/models/{account,brand,creator}.py` | Paired role link; creator uses the shared niche list | D-014 | Impossible profile–account pairs are refused |
| `app/modules/auth/service.py` | Refresh, logout, log out of all devices; login reuses one session helper | D-008 | Sessions can be renewed and ended |
| `app/modules/auth/dependencies.py` | `get_current_account`, `require_role` | D-012 | Protected endpoints have a verified caller |
| `app/modules/auth/tokens.py` | PyJWT's machine-clock checks off; our clock decides | Bug fix | Clock skew no longer logs people out |
| `app/modules/auth/schemas.py`, `exceptions.py` | Profile shapes and errors | Profiles | Readable validation messages |
| `app/main.py` | Four routers wired | — | 22 endpoints live |
| `app/db/models.py` | Campaign and Application registered | — | Alembic sees them |
| `tests/factories.py` | Campaign builder | — | — |
| `docs/DECISIONS.md` | D-014, D-015, D-016 | Decision log | — |
### Deleted
None.

## 4. API changes
All new endpoints are rate limited and documented in `/docs`.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/refresh` | New tokens; reuse ends the login family | Refresh token |
| POST | `/api/v1/auth/logout` | End this login | Refresh token |
| POST | `/api/v1/auth/logout-all` | End every session | Access token |
| GET | `/api/v1/auth/me` | Who am I | Access token |
| POST/GET/PATCH | `/api/v1/brands/me` | Brand profile | Brand |
| POST/GET/PATCH | `/api/v1/creators/me` | Creator profile | Creator |
| POST | `/api/v1/campaigns` | Create a draft | Brand |
| GET | `/api/v1/campaigns` | My campaigns | Brand |
| GET | `/api/v1/campaigns/discover` | Open campaigns, filtered | Any |
| GET/PATCH | `/api/v1/campaigns/{id}` | Read and change | Any / owner |
| POST | `/api/v1/campaigns/{id}/{publish,close,cancel}` | Status changes | Owner |
| POST | `/api/v1/campaigns/{id}/applications` | Apply | Creator |
| GET | `/api/v1/campaigns/{id}/applications` | Applicants | Owner |
| GET | `/api/v1/applications/me` | My applications | Creator |
| GET | `/api/v1/applications/{id}` | One application | Creator or owning brand |
| POST | `/api/v1/applications/{id}/{shortlist,accept,reject}` | Brand decisions | Owning brand |
| POST | `/api/v1/applications/{id}/withdraw` | Take it back | Creator |

## 5. Database changes
| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|
| `25932ee8f40b` link profiles to account role | unique `(id, role)` on account; `account_role` on brand and creator; paired foreign keys | Yes | Mismatched or double profiles refused |
| `b9f74ec5b426` add campaign table | 15 columns, 12 checks, partial index on open campaigns, GIN on niches and cities | Yes | New table |
| `ee268d5e08eb` add application table | 11 columns, 6 checks, unique (campaign, creator), two list indexes | Yes | New table |

`alembic downgrade base` → `upgrade head` rebuilds all 10 migrations; `alembic check` reports no drift.

## 6. Testing
- **Commands run:** `pytest` (repeatedly, final run in wrap-up), per-file runs, `alembic downgrade base`/`upgrade head`/`check`
- **Result:** 449 passed · 0 failed · 0 skipped (1 Starlette deprecation warning)
- **New tests (217):** profile–role 14, refresh service 15, refresh API 17, current account 20, campaign model 44, campaign API 43, profiles 33, applications 31
- **Checks that the tests catch real faults:** removing the profile-role link, and the earlier lock and logging experiments, each made the matching tests fail before being restored.
- **Not verified:** CI results for this push (`gh` is not installed here; check the Actions tab).

## 7. Commits pushed
```
1e5243b feat(campaigns): applications, from pitch to decision
1b4037e feat(auth): brand and creator profile endpoints
7a5859f feat(campaigns): campaign endpoints with ownership and status rules
120c879 feat(campaigns): add campaign table
eeab923 docs: add playbook gap analysis
7712292 feat(auth): refresh, logout, current-account check and backlog
fe07f52 feat(auth): tie each profile to its account role in the database
```
(plus this report's commit)

## 8. Decisions approved today
| ID | Decision | Approved by | Impact |
|---|---|---|---|
| D-014 | Profiles tied to their account's role in the database | Adhi | One migration; closes a review finding |
| D-015 | Money stored as whole paise | Adhi | Every money column from now on |
| D-016 | New `campaigns` module for campaigns and applications | Adhi (**Erode still to confirm**) | Changes the module list in CLAUDE.md section 3 |

## 9. Dependencies
None added or removed.

## 10. Bugs found
| Severity | Description | Status |
|---|---|---|
| High | PyJWT refused tokens whose "issued at" time was ahead of the machine clock, so clock skew between servers would log people out | Fixed in `1e5243b`; our injectable clock decides validity; covered by a test |
| Medium | A campaign budget minimum without a maximum passed, because a comparison with NULL is unknown and an unknown CHECK passes | Fixed in `120c879` before the migration was applied anywhere |
| Low | An unknown campaign type failed the budget rule instead of the type rule, so the message named the wrong problem | Fixed in `120c879` |

## 11. Technical debt
| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| Cities are free text on campaigns and creator profiles | No agreed city list | Low; messy filters later | Decide a Tamil Nadu city list |
| No per-phone verify limit | The rate limiter cannot read the phone from the body | Low | Database-counted limit in the service |
| IP limits use the direct connection address | Not deployed yet | High behind a proxy | Trust `X-Forwarded-For` from the known proxy only |
| Rate-limit storage is in memory | D-003 interim | Medium with more than one process | Move to Redis |
| No way to log in by hand locally | Codes are never logged | Low | Dev-only fixed code, or a local-only endpoint |
| `alembic/env.py` reads `DATABASE_URL` directly | Out of scope | Low | Move to settings |
| Refresh lifetime exists in two places | Model constant used by factories | Low | Keep one source |
| CI runs `alembic upgrade head` only | Carried over | Medium | Add the downgrade round trip |
| No seed script or measured performance | Not built yet | Medium before launch | Seed script, then measure the list endpoints |
| PRs merged without a recorded "Approve" review | Review process still new | Medium | Use "Review changes → Approve" before merging |

## 12. Blockers
| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| D-016 needs the second founder | The new module changes the approved architecture | Confirm, then update CLAUDE.md section 3 | Erode Harish |
| `docs/report-update-2026-09-17` has no PR | Yesterday's report update is not on `main` | Open and merge it | Adhi |
| Phase B policy decisions | Deal memos and payment status cannot start | Proof, approval window, cancellation, late payment, dispute path (see PLAYBOOK_GAPS section 5) | Both founders |
| Validation pack | ASCI, DPDP retention, GST and TDS | Answers from a qualified source | Both founders |

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 22 endpoints; the marketplace core works end to end |
| Database | 🟢 | 10 migrations; round trip and `alembic check` clean |
| APIs | 🟢 | Rate limited, documented, ownership checked, one error shape |
| Tests & CI | 🟡 | 449 tests pass locally; CI for this push not verified; CI still lacks the downgrade check |
| Infrastructure | 🟡 | Proxy-aware IP limits and Redis-backed limits needed before deployment |

## 14. Next recommended tasks
1. **Open the PR for `feature/campaigns`**, and get Erode's confirmation of D-016.
2. **Open the small PR for yesterday's report update.**
3. **Phase B policy decisions** (see above), then build the deal memo.
4. **Payment status with the trust record**: brand marks paid, creator confirms, reliability score from real events.
5. **Seed script and measured performance** for the list endpoints, against the p95 budgets.

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** `feature/campaigns` at the report commit (code at `1e5243b`)
- **Pending:** two PRs; Erode's confirmation of D-016; Phase B decisions.
- **Open questions:** OTP provider? Local login for developers? City list? Pricing model (PLAYBOOK_GAPS section 1)?
- **Watch out for:**
  - Run `alembic upgrade head` after pulling: three new migrations.
  - `.env` needs `OTP_HASH_KEY` and real 32+ character keys.
  - Keep the rate-limit handler synchronous, and never log exception text from OTP providers.
  - Money is whole paise everywhere (D-015).
- **First command to run:** `git fetch origin`, then `alembic upgrade head`
