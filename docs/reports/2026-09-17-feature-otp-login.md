# Daily Engineering Report: 2026-09-17 (session 2)

**Branch:** `feature/otp-login` (built on `feature/creator-model`)  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** not opened. [Open it](https://github.com/adhi2801/nicheconnect-tn/compare/feature/otp-login?expand=1) after the `feature/creator-model` PR is merged.

## 1. Founder summary
- **Phone login works end to end:** request a code, then verify it to get a 15-minute access token and a 30-day refresh token. New numbers get an account automatically.
- **Abuse protection:** limits per phone (3 codes per 10 minutes, 10 per day) and per IP; 5 attempts per code; one generic error for every bad code; a per-phone database lock, proven necessary by tests.
- **Privacy:** codes and refresh tokens are stored only as hashes; registered and unknown numbers get identical responses; no phone, code or token appears in logs (tested).
- **Shared foundations every future endpoint uses:** one standard error format, a request ID on every response, and settings that refuse unsafe keys.
- **Tests:** 232 passing, up from 79. 153 are new, including concurrency tests.
- **Blocked:** the tables PR (`feature/creator-model`) is still not merged into `main`, and this branch builds on it.
- **Next:** refresh and logout endpoints, then the "current user" check, then profile endpoints.

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| Settings hardening (key length, placeholders, distinct keys, 15-minute cap, DB pool and timeout) | Tested | `a853866`, `tests/core/test_config.py` |
| Problem Details error format | Tested | `a853866`, `tests/core/test_errors.py`, `tests/test_rate_limit.py` |
| Request IDs | Tested | `a853866`, `tests/core/test_request_id.py` |
| CI test-only settings | Tested locally | Suite passed with only the CI values and no `.env`; CI run on GitHub not verified |
| Token and code helpers | Tested | `5337c78`, `test_tokens.py` |
| Fake OTP sender with environment guard | Tested | `5337c78`, `test_sender.py` |
| OTP login service (limits, attempts, expiry, roles, lock) | Tested | `5337c78`, `test_otp_service.py`, `test_otp_concurrency.py` |
| `POST /api/v1/auth/otp/request` and `/otp/verify` | Tested | `5337c78`, `test_otp_api.py` |
| Local `.env` updated with generated keys | Implemented | Settings load (checked without printing keys); not committed |
| Commit `a853866` passes on its own | Tested | 116 passed in an isolated checkout |

## 3. Files
### Created
| File | Purpose |
|---|---|
| `app/core/errors.py` | Problem Details handlers, `DomainError`, `ProblemDetails` docs model |
| `app/core/request_id.py` | Request ID middleware |
| `app/modules/auth/exceptions.py` | `invalid_token`, `otp_invalid`, `otp_send_limit_reached`, `role_mismatch` |
| `app/modules/auth/tokens.py` | JWT access tokens, refresh tokens, OTP codes and hashes |
| `app/modules/auth/sender.py` | `OtpSender` interface, fake sender, environment guard |
| `app/modules/auth/service.py` | `request_otp`, `verify_otp`, `deliver_otp` |
| `app/modules/auth/schemas.py` | Request and response models, phone normalisation |
| `app/modules/auth/router.py` | The two endpoints |
| `app/modules/auth/dependencies.py` | `get_now` clock dependency |
| `tests/core/test_config.py`, `test_errors.py`, `test_request_id.py` | Foundation tests |
| `tests/modules/auth/test_tokens.py`, `test_sender.py`, `test_otp_service.py`, `test_schemas.py`, `test_otp_api.py`, `test_otp_concurrency.py` | Login tests |
| `docs/reports/2026-09-17-feature-otp-login.md` | This report |
### Modified
| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `app/core/config.py` | `SecretStr` keys with validation; `otp_hash_key`; refresh lifetime; DB pool and timeout | D-008, D-011, D-012 | App refuses to start with unsafe settings |
| `.env.example` | New settings, comments, port 5433, safe placeholders | backend.md section 8 | Developers must add `OTP_HASH_KEY` and real keys |
| `app/db/session.py` | Uses settings; 5 s statement timeout; `get_db` | database.md section 7 | Queries over 5 s are cancelled |
| `app/main.py` | Error handlers, request-ID middleware, auth router | D-012, D-013 | New endpoints; all errors in one shape |
| `.github/workflows/ci.yml` | Test-only `REDIS_URL`, `SECRET_KEY`, `OTP_HASH_KEY` | CI must load settings | None for users |
| `tests/conftest.py` | Outer transaction with savepoints | Service commits must roll back in tests | None for users |
| `tests/test_rate_limit.py` | Checks the 429 body, `Retry-After` and request ID | Guards against the slowapi fallback bug | None |
| `docs/DECISIONS.md` | D-012, D-013 | Decision log | None |
### Deleted
None.

## 4. API changes
| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/otp/request` | Send a login code | None (public) | Yes: 3 per 10 min per IP; 3 per 10 min and 10 per day per phone | `test_otp_api.py`, `test_otp_service.py`, `test_otp_concurrency.py` |
| POST | `/api/v1/auth/otp/verify` | Log in with a code | None (public) | Yes: 10 per 10 min per IP; 5 attempts per code | `test_otp_api.py`, `test_otp_service.py`, `test_otp_concurrency.py` |
| All | All | Errors now use Problem Details; responses carry `X-Request-ID` | n/a | n/a | `tests/core/` |

## 5. Database changes
None. No migrations on this branch. (Smoke-test rows written to the local database were deleted; it was left empty.)

## 6. Testing
- **Commands run:** `pytest` (full suite several times; final run in wrap-up), per-file `pytest -q tests/...`, isolated run of commit `a853866` with CI-only settings, suite run from a folder with no `.env`
- **Result:** 232 passed · 0 failed · 0 skipped (1 Starlette deprecation warning)
- **New tests (153):** config 15, errors 9, request ID 11, rate limit 2, tokens 25, sender 9, OTP service 23, schemas 31, OTP API 26, concurrency 2
- **Checks that the tests catch real faults:** an async rate-limit handler (the fallback bug) made the 429 test fail; removing the per-phone lock made the concurrency tests fail in 3 of 3 runs. Both were restored.
- **Two service tests can skip** if two random codes happen to be equal (about 1 in a million); the reason is in the skip message.
- **Not verified:** CI results on GitHub.

## 7. Commits pushed
```
5337c78 feat(auth): OTP login endpoints
a853866 feat(core): Problem Details errors, request IDs and safer settings
```
(plus this report's commit)

## 8. Decisions approved today
| ID | Decision | Approved by | Impact |
|---|---|---|---|
| D-012 | Problem Details errors, request IDs, settings hardening, CI test values | Adhi | Every endpoint uses one error shape; `.env` needs new keys |
| D-013 | OTP login flow and token format; `BackgroundTasks` for sending | Adhi | Two public endpoints; job runner still undecided |

## 9. Dependencies
None added or removed on this branch.

## 10. Bugs found
| Severity | Description | Status |
|---|---|---|
| Medium | slowapi silently used its own `{"error": ...}` body because our 429 handler was async; the old test only checked the status | Fixed (handler is synchronous); regression test added |
| Low | A manual check wrote a test account with a realistic number into the local database | Rows deleted; later checks use the rollback fixture |

## 11. Technical debt
| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| No per-phone verify limit (security.md asks 10 per 10 min) | The rate limiter can't read the phone from the body | Low: at most 15 guesses per 10 min and 50 per day per phone | Add a database-counted limit in the service |
| IP limits use the direct connection address | Not deployed yet | High once behind a proxy: all users would share one IP | Trust `X-Forwarded-For` from the known proxy only, before deployment |
| Rate-limit storage is in memory | D-003 interim | Medium with more than one process | Move to Redis before running more than one process |
| No way to log in by hand locally | Codes are never logged | Low | Decide: dev-only fixed code, or local-only endpoint |
| A creator profile can still link to a brand-role account | Carried over | Medium once profile endpoints exist | Check in the profile service |
| `alembic/env.py` reads `DATABASE_URL` directly | Out of scope today | Low | Move to settings |
| Refresh lifetime exists twice (settings and `REFRESH_TOKEN_TTL` in the model) | Model constant used by factories | Low | Keep one source |
| CI runs `alembic upgrade head` only | Carried over | Medium | Add the downgrade round trip (infrastructure approval) |

## 12. Blockers
| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| `feature/creator-model` PR not merged | This branch's PR would also show the tables commits | Open or finish that PR: CI green, review, merge | Adhi, Erode Harish |
| CI result unknown | Can't mark CI green | Check the Actions tab for both branches | Adhi |
| Decisions approved by one founder | D-004 to D-013 need the other founder's review | Review the PRs | Erode Harish |
| OTP provider and DLT rules | Real users can't receive codes | Provider decision; validation pack | Both founders |

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | Login feature complete; shared error and request-ID handling in place |
| Database | 🟢 | No schema changes; local database clean |
| APIs | 🟢 | Two public endpoints, rate limited, documented in `/docs`, tested |
| Tests & CI | 🟡 | 232 local tests pass; CI results not verified; CI lacks the downgrade check |
| Infrastructure | 🟡 | Proxy-aware IP limits and Redis-backed limits needed before deployment |

## 14. Next recommended tasks
1. **Merge `feature/creator-model`**, then open the PR for `feature/otp-login`: this unblocks `main`.
2. **`POST /api/v1/auth/refresh` and `/auth/logout`**: rotation with reuse detection, logout from one device or all.
3. **Current-user dependency**: reads the access token, loads the account and checks the role on protected endpoints.
4. **Creator and brand profile endpoints**, including the account-role check.
5. **Before deployment:** proxy-aware IP limits, Redis-backed rate limits, `/readyz` checks.

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** `feature/otp-login` at the report commit (code at `5337c78`)
- **Pending:** PRs for `feature/creator-model` and `feature/otp-login`; CI status; refresh and logout endpoints.
- **Open questions:** OTP provider? How should developers log in locally? Per-phone verify limit now or later? Erode's review of D-004 to D-013.
- **Watch out for:** Update `.env` from `.env.example` (new `OTP_HASH_KEY`, real 32+ character keys, `ACCESS_TOKEN_EXPIRE_MINUTES=15`), or the app and tests won't start. Keep the rate-limit handler synchronous. `test_otp_concurrency.py` commits real rows for `+917777700001` and cleans them up.
- **First command to run:** `git fetch origin`
