# Daily Engineering Report: 2026-09-17 (sessions 2 and 3)

**Branch:** `feature/otp-login` (merged)  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** [#7](https://github.com/adhi2801/nicheconnect-tn/pull/7) merged into `main` (after [#5](https://github.com/adhi2801/nicheconnect-tn/pull/5))

## 1. Founder summary
- **Phone login is on `main`:** request a code, then verify it to get a 15-minute access token and a 30-day refresh token. New numbers get an account automatically.
- **Both PRs merged** (#5 tables, #7 login), with CI green on both branches and on `main` afterwards. Merged from the other founder's GitHub account; no formal "Approve" review was recorded.
- **Abuse protection:** per-phone limits (3 codes per 10 minutes, 10 per day) and per-IP limits; 5 attempts per code; one generic error for every bad code; a per-phone database lock, proven necessary by tests.
- **Privacy bug found by the automated PR review and fixed before merge:** a failed code delivery could have logged the phone number and live code inside the error details. Only the error type is logged now, and the tests check the full log output.
- **Shared foundations every future endpoint uses:** one error format, a request ID on every response, settings that refuse unsafe keys.
- **Tests:** 232 passing on `main`, up from 79 at the start of this branch.
- **Next:** database fix tying each profile to its account's role (flagged by the automated review on #5), then refresh and logout endpoints.

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| Settings hardening (key length, placeholders, distinct keys, 15-minute cap, DB pool and timeout) | Tested | `a853866`, `tests/core/test_config.py` |
| Problem Details error format | Tested | `a853866`, `tests/core/test_errors.py`, `tests/test_rate_limit.py` |
| Request IDs | Tested | `a853866`, `tests/core/test_request_id.py` |
| CI test-only settings | Tested | Suite passed locally with only the CI values; GitHub CI green on `5208683` and on `main` (`0b17a1e`) |
| Token and code helpers | Tested | `5337c78`, `test_tokens.py` |
| Fake OTP sender with environment guard | Tested | `5337c78`, `test_sender.py` |
| OTP login service (limits, attempts, expiry, roles, lock) | Tested | `5337c78`, `test_otp_service.py`, `test_otp_concurrency.py` |
| `POST /api/v1/auth/otp/request` and `/otp/verify` | Tested | `5337c78`, `test_otp_api.py` |
| Fix: no provider error text in send-failure logs | Tested | `5208683`, `test_send_failure_does_not_break_the_request`, `test_codes_phones_and_tokens_never_reach_the_logs` |
| PRs #5 and #7 merged into `main` | Done | Merge commits `6da8cf0`, `0b17a1e` |
| Local `main` matches the merged work | Tested | No diff from `5208683`; `alembic check` clean; 232 passed on `main` |
| Local `.env` updated with generated keys | Implemented | Settings load (checked without printing keys); not committed |

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
| `app/modules/auth/service.py` (session 3) | `deliver_otp` logs only the error type | Review finding on #7 | Provider errors can't leak phone or code into logs |
| `tests/modules/auth/test_otp_api.py` (session 3) | Log checks use the full formatted output | The earlier check only read the message line | Stronger privacy test |
| `docs/DECISIONS.md` | D-012, D-013 | Decision log | None |
| `docs/reports/2026-09-17-feature-otp-login.md` (session 3) | This update | Wrap-up | None |
### Deleted
None.

## 4. API changes
| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/otp/request` | Send a login code | None (public) | Yes: 3 per 10 min per IP; 3 per 10 min and 10 per day per phone | `test_otp_api.py`, `test_otp_service.py`, `test_otp_concurrency.py` |
| POST | `/api/v1/auth/otp/verify` | Log in with a code | None (public) | Yes: 10 per 10 min per IP; 5 attempts per code | `test_otp_api.py`, `test_otp_service.py`, `test_otp_concurrency.py` |
| All | All | Errors use Problem Details; responses carry `X-Request-ID` | n/a | n/a | `tests/core/` |

## 5. Database changes
None on this branch. `main` is at migration `3d218c522ec6` (from #5); `alembic check` reports no drift.

## 6. Testing
- **Commands run:** `pytest` (full suite several times, including on merged `main`), per-file runs, an isolated run of commit `a853866` with CI-only settings, a suite run with no `.env`, `alembic heads`/`current`/`check`
- **Result:** 232 passed · 0 failed · 0 skipped (1 Starlette deprecation warning)
- **GitHub CI:** success on `ee85a10` (#5), `e8a4120` and `5208683` (#7), and `0b17a1e` (`main`)
- **New tests (153):** config 15, errors 9, request ID 11, rate limit 2, tokens 25, sender 9, OTP service 23, schemas 31, OTP API 26, concurrency 2
- **Checks that the tests catch real faults:**
  - an async rate-limit handler made the 429 test fail
  - removing the per-phone lock made the concurrency tests fail in 3 of 3 runs
  - logging with the traceback attached made the send-failure test fail and show the leaked code and phone
  - all three were restored
- **Correction to the session 2 report:** it said no phone or code reached the logs. That was only true for the message line; the attached error text could contain both. Fixed in `5208683`.
- **Two service tests can skip** if two random codes happen to be equal (about 1 in a million); the reason is in the skip message.

## 7. Commits pushed
```
5208683 fix(auth): keep provider error text out of OTP send-failure logs
e8a4120 docs: add engineering report 2026-09-17 (session 2)
5337c78 feat(auth): OTP login endpoints
a853866 feat(core): Problem Details errors, request IDs and safer settings
```
Merged into `main` as `0b17a1e` (after `6da8cf0` for #5). This update is on `docs/report-update-2026-09-17`.

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
| High | Send-failure logging attached the provider's error text, which can contain the phone number and live code (found by the automated review on #7) | Fixed in `5208683` before merge; test strengthened and shown to catch it |
| Medium | slowapi silently used its own `{"error": ...}` body because our 429 handler was async; the old test only checked the status | Fixed (handler is synchronous); regression test added |
| Low | A manual check wrote a test account with a realistic number into the local database | Rows deleted; later checks use the rollback fixture |

## 11. Technical debt
| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| A profile can link to an account of the other role, or one account to both profiles (automated review on #5) | Plain foreign keys only | Medium once profile endpoints exist | Database-level fix: tie each profile to its account's role (schema approval needed). Next task |
| No per-phone verify limit (security.md asks 10 per 10 min; automated review on #7) | The rate limiter can't read the phone from the body | Low: at most 15 guesses per 10 min and 50 per day per phone | Database-counted limit in the service, before launch |
| IP limits use the direct connection address | Not deployed yet | High once behind a proxy: all users would share one IP | Trust `X-Forwarded-For` from the known proxy only, before deployment |
| Rate-limit storage is in memory | D-003 interim | Medium with more than one process | Move to Redis before running more than one process |
| No way to log in by hand locally | Codes are never logged | Low | Decide: dev-only fixed code, or local-only endpoint |
| `alembic/env.py` reads `DATABASE_URL` directly | Out of scope | Low | Move to settings |
| Refresh lifetime exists twice (settings and `REFRESH_TOKEN_TTL` in the model) | Model constant used by factories | Low | Keep one source |
| CI runs `alembic upgrade head` only | Carried over | Medium | Add the downgrade round trip (infrastructure approval) |
| PRs merged without a recorded "Approve" review | Review process still new | Medium: rule and cross-track decisions need both founders | Use GitHub's "Review changes → Approve" before merging |

## 12. Blockers
| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| Decisions approved by one founder | D-004 to D-013 are on `main` without a recorded second approval | Confirm them (a comment on the PRs or the decision log is enough) | Erode Harish |
| OTP provider and DLT rules | Real users can't receive codes | Provider decision; validation pack | Both founders |

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | Login feature on `main`; shared error and request-ID handling in place |
| Database | 🟢 | `main` at head; no drift; local database clean |
| APIs | 🟢 | Two public endpoints, rate limited, documented in `/docs`, tested |
| Tests & CI | 🟢 | 232 tests pass locally; GitHub CI green on both PRs and on `main`. CI still lacks the downgrade check |
| Infrastructure | 🟡 | Proxy-aware IP limits and Redis-backed limits needed before deployment |

## 14. Next recommended tasks
1. **Profile–role database fix** (automated review on #5): each profile must match its account's role, and one account can't own both profiles. Schema proposal first.
2. **`POST /api/v1/auth/refresh` and `/auth/logout`**: rotation with reuse detection, logout from one device or all.
3. **Current-user dependency**: reads the access token, loads the account and checks the role on protected endpoints.
4. **Per-phone verify limit** (automated review on #7).
5. **Creator and brand profile endpoints.**
6. **Before deployment:** proxy-aware IP limits, Redis-backed rate limits, `/readyz` checks.

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** `main` at `0b17a1e` (this report is on `docs/report-update-2026-09-17`)
- **Pending:** PR for this report update; the profile–role fix proposal.
- **Open questions:** OTP provider? How should developers log in locally? Erode's confirmation of D-004 to D-013.
- **Watch out for:**
  - Everyone runs `git checkout main`, `git pull` and `pip install -r requirements.txt`.
  - Update `.env` from `.env.example` (new `OTP_HASH_KEY`, real 32+ character keys, `ACCESS_TOKEN_EXPIRE_MINUTES=15`), or the app and tests won't start. Then run `alembic upgrade head`.
  - Keep the rate-limit handler synchronous.
  - Never log exception text from OTP providers.
- **First command to run:** `git checkout main`, then `git pull`
