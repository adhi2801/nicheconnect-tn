# Daily Engineering Report: 2026-09-22

**Branch:** `chore/cors-and-docs`  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** not opened. Open it with base `feature/attention`: [compare](https://github.com/adhi2801/nicheconnect-tn/compare/feature/attention...chore/cors-and-docs?expand=1)

This is the second report for 2026-09-22. The first, `2026-09-22-feature-attention.md`, covers the morning's "what needs my attention" feature. This branch starts from that report's commit (`577b9e7`), so it is stacked on PR #13.

## 1. Founder summary

- **Browser access is locked down.** Only websites listed in the new `CORS_ALLOWED_ORIGINS` setting may call the API from a browser, and the list is empty by default. Each entry is checked at startup: `*` is refused, `https://` is required once deployed, cookies from other sites are refused, and a near-miss like `https://app.com/` stops the app with the exact text to write instead. The mobile app is unaffected.
- **A crash now reaches the dashboard readably.** Found and fixed an older gap: a 500 went out without any security headers, although 404 and 200 answers had them. Now 413, 429 and 500 answers all carry the CORS permission, the security headers and the request ID.
- **API docs are off in production.** `/docs`, `/redoc` and `/openapi.json` answer 404 there, and still work in local, test and staging.
- **Environment typos stop the app.** `ENVIRONMENT` must be `local`, `test`, `staging` or `production`. `prod` used to be accepted without any warning.
- **Tests: 1,172 passing**, up from 1,102. Lint, formatting and strict types are clean, and coverage is 98.1%. Every rule was broken on purpose and a test failed each time.
- **Two decisions recorded:** D-044 (CORS, docs, environments) and D-045 (the 500 fix), both approved by Adhi in this session.
- **The message for Erode Harish is now in the repo, not sent separately.** The notice in PR #12 was updated and pushed. It reaches Erode Harish's sessions **only once PR #12 is on `main`.**
- **Still blocked on Erode Harish:** the review of PR #13, which holds migrations 17 to 20, and rate card decision 1.

## 2. Work completed

| Task | Status | Evidence |
|---|---|---|
| `ENVIRONMENT` limited to four known values | Tested | `a81be23`; `test_unknown_environment_stops_the_app` |
| `CORS_ALLOWED_ORIGINS` setting, checked at startup | Tested | `a81be23`, `55519c7`; `test_a_near_miss_origin_is_refused_with_the_form_to_use` and 25 more |
| CORS rules: closed lists of websites, methods and headers, no cookies | Tested | `96beba2`; `tests/core/test_cors.py` (19 tests, two of them read the real API contract) |
| 500 answers get every header (pre-existing gap) | Tested | `8f29a6b`; `tests/core/test_unexpected_error.py`, including `test_without_this_layer_a_500_misses_the_security_headers` |
| CORS and the error layer switched on in the right order; docs off in production | Tested | `2eb1561`; `tests/test_main.py` starts the real app in a fresh process for production and for an allowed website |
| `.env.example` documents the new setting, and tests keep it in step with the settings | Tested | `1d31230`; `test_every_setting_is_listed_in_env_example`, `test_the_example_values_load` |
| `security.md` updated; `/docs` item ticked | Implemented (docs only) | `471b85d` |
| Notice for Erode Harish updated with today's asks | Implemented, pushed | `886d7d6` on `docs/notice-for-erode` (PR #12); CI green on that commit |

## 3. Files

### Created

| File | Purpose |
|---|---|
| `app/core/cors.py` | The CORS rules: websites, methods, headers a page may send and read, no cookies, preflight cache |
| `app/core/unexpected_error.py` | Turns an unexpected error into the usual 500 inside the middleware, so it gets every header |
| `tests/core/test_cors.py` | Browser-style checks of the CORS rules, plus two checks against the real API contract |
| `tests/core/test_unexpected_error.py` | The 500 fix, including a test that shows the gap without it |
| `tests/test_main.py` | Middleware order, and the real app started in a fresh process for production and for an allowed website |
| `docs/reports/2026-09-22-chore-cors-and-docs.md` | This report |

### Modified

| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `app/core/config.py` | `ENVIRONMENT` limited to four values; new `cors_allowed_origins` with startup checks | D-044 | An unknown environment or an unusable website entry stops the app at startup |
| `app/main.py` | Adds CORS and the error layer; docs URLs off in production | D-044, D-045 | Browser access follows the allow-list; 500s carry every header; no docs in production |
| `app/core/security_headers.py` | One comment corrected | It still called the `/docs` question open | None |
| `.env.example` | `CORS_ALLOWED_ORIGINS` added; `ENVIRONMENT` lists all four values | `backend.md` section 8 | None; the new setting is optional |
| `tests/core/test_config.py` | 39 new tests | Environment, CORS setting, `.env.example` | None |
| `docs/DECISIONS.md` | D-044, D-045 | Approved in this session | None |
| `docs/standards/security.md` | Section 7 names the CORS rules and 500 headers; section 9 ticks `/docs` | D-044, D-045 | None |
| `CLAUDE.md` (on `docs/notice-for-erode` only) | Section 0 notice updated | Adhi's message to Erode Harish goes through the repo | Erode Harish's sessions show it once PR #12 is on `main` |

### Deleted

None.

## 4. API changes

No new endpoints. The API contract (`docs/api/openapi.json`) is unchanged, and the contract guard passes.

| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|
| GET | `/docs`, `/redoc`, `/openapi.json` | Now 404 when `ENVIRONMENT=production`; unchanged elsewhere | None | Yes (default 60/min) | `test_the_api_docs_are_gone_in_production`, `test_the_api_docs_are_served_outside_production` |
| OPTIONS | any path | Browser preflight, answered by the CORS layer: 200 for an allowed website, 400 otherwise | None | No. This is unchanged: slowapi already skipped every OPTIONS request (D-044) | `tests/core/test_cors.py` |
| All | all paths | 500 answers now carry the security headers and, for an allowed website, CORS permission | As before | As before | `tests/core/test_unexpected_error.py`, `test_every_kind_of_answer_reaches_the_dashboard_readably` |

## 5. Database changes

| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|
| None | None | n/a | None |

## 6. Testing

- **Commands run (this session):**
  - `venv/Scripts/python.exe -m pytest -o addopts="" -q` (full suite, after each file)
  - `venv/Scripts/python.exe -m pytest -x --tb=short --cov --cov-report=term` (as CI runs it), then `coverage json` to check every `service.py`
  - `venv/Scripts/python.exe -m pytest` (wrap-up)
  - `ruff check .`, `ruff format --check .` and `mypy`
- **Result:** 1,172 passed · 0 failed · 0 skipped (59 s). Coverage 98.11% overall (floor 80%). The lowest `service.py` is `deal_memo/service.py` at 94.4% (floor 90%). `cors.py`, `unexpected_error.py`, `config.py` and `main.py` are at 100%. Ruff and strict mypy (96 files) are clean.
- **Break-it checks:** each rule was broken on purpose with the tests re-run: 6 in `config.py`, 8 in `cors.py`, 3 in `unexpected_error.py`, 4 in `main.py` and 3 in `.env.example`. A test failed every time. Two first attempts proved nothing and were redone. The wildcard message had no test, so one was added. The "answer already started" test passed for the wrong reason, because any `RuntimeError` satisfied it, so it now requires the original error. One test filter selected no tests; it was re-run with the right filter.
- **CI:** GitHub Actions was still running on `471b85d` when this report was written ([run](https://github.com/adhi2801/nicheconnect-tn/actions/runs/35654807889)). Its result is **not verified here**. It passed on `886d7d6` (the notice branch).
- **New tests:** 70. That is 39 in `test_config.py`, 19 in `test_cors.py`, 8 in `test_unexpected_error.py` and 4 in `test_main.py`.
- **Warnings:** 2, both from Starlette's test client library (`httpx` to `httpx2`, and an `anyio` alias), not from our code.

## 7. Commits pushed

```
471b85d docs(security): CORS, 500 headers and /docs decided (D-044, D-045)
55519c7 refactor(core): drop an origin check that could never run
1d31230 chore(config): document CORS_ALLOWED_ORIGINS, and test .env.example itself (D-044)
2eb1561 feat(api): switch on CORS and the error layer; API docs off in production (D-044, D-045)
8f29a6b fix(core): an unexpected error gets every header a normal answer gets (D-045)
96beba2 feat(core): the CORS rules, closed lists only (D-044)
a81be23 feat(core): only known environments, and a checked CORS allow-list (D-044)
```

Also pushed, on `docs/notice-for-erode`:

```
886d7d6 docs: update the notice for Erode Harish with the 22 September asks
```

This report is committed and pushed on `chore/cors-and-docs`.

## 8. Decisions approved today

| ID | Decision | Approved by | Impact |
|---|---|---|---|
| D-044 | CORS allow-list, API docs off in production, only known environments | Adhi (option A, including answering preflights before the rate limiter) | One new optional setting; the app refuses unknown environments and unusable website entries |
| D-045 | Unexpected errors answered inside the middleware | Adhi (option A) | 500s carry every header; body and log line unchanged |

## 9. Dependencies

None. CORS uses Starlette's own middleware, which is already installed.

## 10. Bugs found

| Severity | Description | Status |
|---|---|---|
| Medium | 500 answers had no `Content-Security-Policy` or `X-Content-Type-Options`, because Starlette runs the catch-all error handler outside all middleware. It dates from the security headers work (`94b89d8`, 20 Sep). With CORS on, the dashboard could not have read a 500 at all | Fixed in `8f29a6b`, tested |

## 11. Technical debt

| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| The "local environments" set is written out in three places (`config.PLAIN_HTTP_ENVIRONMENTS`, `security_headers.LOCAL_ENVIRONMENTS`, `sender.FAKE_SENDER_ENVIRONMENTS`) | Each was added with its own feature | Low, now that `ENVIRONMENT` only accepts four values | Import one constant from `config.py` |
| `TRUSTED_PROXIES` silently skips an entry it can't read, while `CORS_ALLOWED_ORIGINS` stops the app | Written at different times | A mistyped proxy range puts every user in one rate-limit bucket, without warning | Check it at startup the same way (security area: needs approval) |
| A refused preflight answers Starlette's plain-text 400, not Problem Details | Starlette's CORS middleware builds it | Low: the browser reads it, the page never sees it | Leave it |
| Starlette test client deprecation warnings | Upstream is moving from `httpx` to `httpx2` | None today | Handle at the next dependency upgrade (needs approval) |
| Carried: `coverage` not pinned; `/docs` CSP allows inline scripts | See the 2026-09-21 report | As before, and `/docs` now only outside production | As before |

**Resolved today from the carried list:** "no CORS allow-list" and "`/docs` in production".

## 12. Blockers

| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| Review of PR #13, including migrations 17 to 20 | Nothing merges to `main`, and this branch is stacked on #13 | Review, and agreement to close #11 | Erode Harish |
| The notice reaches Erode Harish's sessions only from `main` | The message isn't sent any other way, so until PR #12 is merged Erode Harish may not see it | Merge PR #12 on GitHub. Our rule asks for the other founder's review first, which is circular for a notice addressed to that founder. Adhi's decision | Adhi |
| Rate card decision 1 | The top competitive feature can't be built | Decision (two tables, one column) | Both founders |
| Brand and creator records public or not; DPDP retention (carried) | Both records stay behind a login | Decision, and the validation pack | Both founders |

## 13. Health

| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 1,172 tests, strict types, lint clean |
| Database | 🟡 | No change today; migrations 17 to 20 still waiting for their track owner's review |
| APIs | 🟢 | Contract unchanged; browser access now follows an allow-list; errors readable by the dashboard |
| Tests & CI | 🟢 | Everything passes locally with coverage gates. CI on this branch was still running at the time of writing |
| Infrastructure | 🔴 | Still no hosting, backups or job runner, although two pre-production items are now done |

## 14. Next recommended tasks

1. **Adhi decides whether to merge PR #12 now**, so the notice, and with it the message, reaches Erode Harish's next session. Otherwise the review of #13 has no route to Erode Harish.
2. **Erode Harish reviews PR #13, then this branch's PR.** Every merge to `main` waits on it.
3. **Rate card decision 1 with both founders.** It unblocks the next feature on the competitive build list.

_Not started automatically. Awaiting founder approval._

## 15. Handoff

- **Pick up from:** `chore/cors-and-docs`, at the report commit after `471b85d`. Pushed; no PR open yet.
- **Pending:** open the PR on GitHub with base `feature/attention` (the compare link at the top). Suggested text is in this session's chat.
- **Open questions:** merge PR #12 now? Close #11 in favour of #13? Rate card decision 1.
- **Watch out for:**
  - Merge order: #13 first, then this branch. If `feature/attention` is deleted after #13 merges, GitHub moves this PR's base to `main` on its own.
  - `ENVIRONMENT` now refuses anything but the four values. A `.env` with another value stops the app, and the error names the valid ones.
  - To try a dashboard locally, set `CORS_ALLOWED_ORIGINS=http://localhost:5173` in `.env`.
  - On Adhi's laptop, bare `python` points at another project's venv. Use `venv\Scripts\python.exe`.
- **First command to run:** `git fetch origin`
