# Daily Engineering Report: 2026-09-20

**Branch:** `feature/creator-passport`  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** not opened — https://github.com/adhi2801/nicheconnect-tn/compare/feature/creator-passport?expand=1

## 1. Founder summary

- **The public Creator Passport is built.** `GET /api/v1/creators/by-handle/{handle}` answers without a login, so a creator can put the link in an Instagram bio and every visitor lands on the product. It returns eight agreed fields and nothing else.
- **Before it can go live, one thing is missing:** a creator who signed up only to browse has no way to say "don't publish me". That switch is a column on the creator table, which is the Data track's file. The endpoint already has the single line it plugs into. **Do not deploy the Passport until that column exists.**
- **We were running a web layer with 16 known security holes.** An audit of our pinned packages found eight in Starlette alone, including an unvalidated `Host` header and request bodies that buffer without limit — reachable by anyone, no login needed. Upgraded and now clean.
- **CI will catch the next one by itself.** A `pip-audit` step now blocks merge on any known vulnerability.
- **Request bodies are now capped at 1 MB.** Our own security standard claimed this control; nothing enforced it. Now two checks do.
- **Security headers now go out on every response** — the second of the three gaps found today, closed. A test guards the `/docs` page against a future CDN change breaking it.
- **One gap left:** a CORS allow-list, which genuinely can't be built until a frontend origin exists.
- **You can now download everything we hold about you.** `GET /api/v1/me/export` returns one self-explaining JSON file. It is built so that forgetting a table is impossible: a test fails until every table is either exported or has a written reason not to be.
- **A retried application no longer submits twice.** `Idempotency-Key` is now honoured: a creator whose connection drops mid-apply gets their original answer back instead of a confusing "you already applied". This is the fourth control our own standards claimed and nothing implemented.
- **Tests:** 748 passing, up from 599 at the last report. Nothing is broken.
- **Waiting on Erode Harish:** the `payment_status` table. Everything about money, reliability scores and disputes is blocked behind it.

## 2. Work completed

| Task | Status | Evidence |
|---|---|---|
| Public Creator Passport endpoint | Tested | `e7cabff`; 20 tests in `tests/modules/auth/test_public_profile_api.py` |
| Dependency vulnerability audit of the pinned set | Tested | `pip-audit` run this session: 16 findings before, "No known vulnerabilities found" after |
| Upgrade FastAPI, Starlette, pytest | Tested | `552367d`; full suite passed on the new versions before the pins changed |
| `pip-audit` as a CI gate | Implemented | `552367d`; the exact command was run locally and exits 0. Not yet seen green on GitHub Actions |
| Request body size limit | Tested | `2f4b662`; 18 tests in `tests/core/test_body_limit.py` |
| Security headers on every response | Tested | `94b89d8`; 26 tests in `tests/core/test_security_headers.py` |
| Data export (`GET /api/v1/me/export`) | Tested | `828c208`; 43 tests in `tests/modules/auth/test_export_api.py` |
| `Idempotency-Key` on application POSTs | Tested | `a946a92`; 42 tests across `tests/core/test_idempotency.py` and `tests/modules/campaigns/test_application_idempotency_api.py` |
| Decision D-031 recorded | Tested | `552367d`, `docs/DECISIONS.md` |
| Assignment file for 19 Sep committed | Implemented | `4d8d91c` |

## 3. Files

### Created

| File | Purpose |
|---|---|
| `app/modules/auth/public_router.py` | The public Creator Passport: one read-only endpoint, no login |
| `tests/modules/auth/test_public_profile_api.py` | 20 tests, including an exact-field-set contract test |
| `app/core/body_limit.py` | Refuses request bodies over 1 MB, by declared size and by real size |
| `tests/core/test_body_limit.py` | 18 tests, including chunked bodies and a lying `Content-Length` |
| `app/core/security_headers.py` | nosniff, Referrer-Policy, X-Frame-Options, CSP and HSTS on every response |
| `tests/core/test_security_headers.py` | 26 tests, including a guard that the CSP covers what `/docs` really loads |
| `app/core/export.py` | Declared fields, secret-name refusal, row caps and JSON conversion for exports |
| `app/modules/auth/export_service.py` | Assembles the export, the manifest, and what is deliberately withheld |
| `app/modules/auth/export_router.py` | `GET /api/v1/me/export` |
| `tests/modules/auth/test_export_api.py` | 43 tests, including the table-completeness guard |
| `app/core/idempotency.py` | The claim/replay state machine, in Redis |
| `app/core/idempotent_route.py` | Applies it to a whole router without touching endpoints |
| `app/core/redis_client.py` | One shared Redis connection pool |
| `tests/core/test_idempotency.py` · `tests/modules/campaigns/test_application_idempotency_api.py` | 42 tests |
| `docs/assignments/2026-09-19.md` | Yesterday's task assignment, previously uncommitted |

### Modified

| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `requirements.txt` | `fastapi` 0.115.0→0.141.1, `pytest` 8.3.3→9.1.1, new explicit `starlette==1.6.0` | 16 known vulnerabilities in the old pins | Everyone must re-run `pip install -r requirements.txt` |
| `.github/workflows/ci.yml` | Added the `pip-audit` step as gate 6 | `security.md` section 8 | A known vulnerability now blocks merge |
| `app/main.py` | Registered the public router, `BodyLimitMiddleware` and `SecurityHeadersMiddleware` | Wiring | Public endpoint live; every request body capped; every response carries security headers |
| `app/modules/campaigns/service.py` | Declares its campaign and application export sections | Each module owns its own export shape | None to existing endpoints |
| `app/modules/deal_memo/service.py` | Declares its memo and proof export sections | As above | None to existing endpoints |
| `app/modules/notifications/service.py` | Declares its notification export section | As above | None to existing endpoints |
| `app/modules/auth/tokens.py` | Split signature checking from expiry checking; added `account_id_for_scoping` | Idempotency needs to know *whose* request this is without caring that a token just lapsed | None to authentication |
| `app/modules/auth/dependencies.py` | Added `idempotency_identity` | Resolves a request to its verified account | None |
| `app/modules/campaigns/application_router.py` | Built with `route_class=IdempotentRoute` | Every POST here now accepts `Idempotency-Key` | Requests without the header are unchanged |
| `docs/DECISIONS.md` | Added D-031 | Approval record | None |

### Deleted

None.

## 4. API changes

| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|
| GET | `/api/v1/creators/by-handle/{handle}` | Public Creator Passport | **None — public** | 60/min | 20 |
| GET | `/api/v1/me/export` | Download everything we hold about you | Any signed-in account | 3/hour | 43 |

Public fields: `id`, `handle`, `display_name`, `city`, `niches`, `languages`, `bio`, `member_since`. Deliberately excluded: `account_id`, phone, email, `updated_at`. A test asserts the exact field set, so a column added later cannot leak in by accident.

The endpoint caches for 5 minutes and supports `ETag` / `If-None-Match`, because a link in a bio is read far more often than it changes.

Every response now carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` and a Content-Security-Policy — `default-src 'none'` for JSON, and a wider, explicit policy for the `/docs` and `/redoc` HTML so the API documentation still works. HSTS is sent only outside local and test.

Every POST under `/api/v1/campaigns/{id}/applications` and `/api/v1/applications/...` now accepts an optional **`Idempotency-Key`** header: same key and body replays the original response with `Idempotency-Replayed: true`, a retry while the first is still running gives 409, and a key reused with a different body gives 422. Keys are remembered for 24 hours. The header is in the OpenAPI contract for exactly those routes.

Every other endpoint now returns **413** with the standard Problem Details body when the request body exceeds 1 MB.

## 5. Database changes

| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|
| None | — | — | No schema change today |

## 6. Testing

- **Commands run:** `pytest -q` · `pip-audit --requirement requirements.txt --strict --desc` · an OpenAPI generation check · a direct check that the chunked-body test exercises the counting path rather than the header path · a direct check of which origins `/docs` and `/redoc` actually reference
- **Result:** **748 passed, 2 warnings, 30.35s**, re-run against a database holding 1,000+ seeded rows to prove no test assumes an empty table. 0 failed, 0 skipped. `pip-audit` exit 0, "No known vulnerabilities found". OpenAPI generates 40 paths / 49 operations, every one with a summary, `ProblemDetails` present.
- **New tests:** 20 for the public Passport, 18 for the body limit, 26 for the security headers, 43 for the export, 42 for idempotency.
- **Idempotency tests use real Redis** on database 2, kept apart from the rate-limit tests (database 1) and the app (database 0). CI already runs a Redis service.
- **Measured on the export:** 93 records in **13 queries, 26 ms, 53 KB** on seeded data — constant query count, no N+1, well inside the 300 ms read budget.
- **Not verified:** CI has not run on GitHub Actions yet. The `pip-audit` step is expected to pass because the identical command passes locally, but it has not been seen green on a runner.
- The 2 warnings come from Starlette's own test client (`anyio` deprecations). Upstream, not ours.

## 7. Commits pushed

```
a946a92 feat(api): Idempotency-Key, so a retried request runs once
0161976 test(privacy): flag the one allowed use of the forbidden payment words
828c208 feat(privacy): download everything we hold about you
ca286c4 docs: update the 2026-09-20 report with the security headers work
94b89d8 feat(core): security headers on every response
5ebf392 docs: add engineering report 2026-09-20
4d8d91c docs: add the task assignment for 2026-09-19
2f4b662 feat(core): refuse request bodies over 1 MB
552367d chore(deps): upgrade FastAPI, Starlette and pytest, and audit in CI
e7cabff feat(auth): public Creator Passport, readable without logging in
```

## 8. Decisions approved today

| ID | Decision | Approved by | Impact |
|---|---|---|---|
| D-031 | Upgrade FastAPI, Starlette and pytest; audit dependencies in CI | Adhi | Three pins changed, one new CI gate, Starlette now pinned explicitly |

## 9. Dependencies

| Package | Version | Reason | Approval ref |
|---|---|---|---|
| `fastapi` | 0.115.0 → 0.141.1 | Only way to move off the vulnerable Starlette | D-031 |
| `starlette` | 0.38.6 → 1.6.0 | 8 advisories, including unvalidated `Host` and unbounded multipart buffering | D-031 |
| `pytest` | 8.3.3 → 9.1.1 | PYSEC-2026-1845 | D-031 |
| `pip-audit` | 2.10.1 | CI gate only — deliberately **not** in `requirements.txt`, so its dependencies stay out of the running app | D-031 |

## 10. Bugs found

| Severity | Description | Status |
|---|---|---|
| High | Starlette did not validate the `Host` header, injecting a path into `request.url` | Fixed by upgrade |
| High | Multipart text fields buffered without limit — memory exhaustion, no login needed | Fixed by upgrade |
| High | `max_fields` / `max_part_size` silently ignored on urlencoded forms, so limits we thought were set did nothing | Fixed by upgrade |
| Medium | FastAPI 0.141.1 allows `starlette>=0.46.0` with no upper bound, and advisories in that range stay open until 1.3.1 — a fresh install could have drifted back onto a vulnerable version | Fixed by pinning Starlette explicitly |
| Medium | No request body size limit existed, though `security.md` section 3 claims one | Fixed in `2f4b662` |
| Medium | No security headers existed, though `security.md` section 7 claims four of them | Fixed in `94b89d8` |
| Low | `pytest` local temp-directory issue (PYSEC-2026-1845) | Fixed by upgrade |
| Medium | Idempotency scoped by the raw access token, so a client that refreshed its token between a dropped request and its retry would have double-submitted — the exact failure the feature prevents. Found by a test, not by reasoning | Fixed in `a946a92`: retries are grouped by verified account |

## 11. Technical debt

| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| Creators cannot opt out of the public Passport | The switch is a column on the creator table, which belongs to the Data track | **Blocks deployment.** Someone who signed up only to browse is published without consent | One column plus a migration; `passport_is_public()` is the only line that changes |
| No CORS allow-list | No frontend origin exists yet to allow | Low today, blocking the day a frontend appears | Decide origins when frontend work starts (D-004) |
| `/docs` CSP allows `'unsafe-inline'` scripts | FastAPI generates an inline bootstrap script we don't control | Confined to two developer-facing pages | `security.md` section 9 still requires a decision on whether `/docs` is reachable in production at all |
| Body limit is a module constant, not config | Avoids adding an environment variable before anyone needs to tune it | Low | Move to `config.py` when a deployment needs a different value |

## 12. Blockers

| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| `payment_status` table does not exist | Payment handshake, brand reliability record, late/unpaid states and disputes cannot start | The table and its migration (D-027) | Erode Harish |
| Creator opt-out column | Passport cannot be deployed | One column plus migration | Erode Harish |
| Media storage undecided | Half of D-024 (screenshots, recordings) cannot be built | A decision: cloud bucket or database | Both founders |
| Job runner undecided | Reminders cannot be sent. Auto-approval already works without one | A decision | Both founders |
| Who the pilot serves (D-030 point 4) | Changes the account model; team support cannot start | A decision | Both founders |

## 13. Health

| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 637 tests pass, 49 documented operations, one error shape throughout |
| Database | 🟢 | 16 migrations rebuild an empty database cleanly. No change today |
| APIs | 🟡 | Solid, but the public Passport must not deploy before the opt-out column |
| Tests & CI | 🟢 | No failures, no skips, and a dependency audit now guards merges |
| Infrastructure | 🔴 | No hosting, no backups, no job runner. Nothing deployed |

## 13a. Open questions for the other founder

Two calls on the export that are a founder's, not mine. Both are live in the code now and easy to change:

1. **A brand's export includes the pitches creators wrote to them.** That is the brand's own business record, and the creator appears only by public handle — no phone, no email. But it is still text another person authored. Reasonable either way; say if you want it out.
2. **Login session metadata is included** (when you signed in, when it expires, whether it was logged out — never the tokens). Useful for "where am I signed in", but nobody asked for it.

## 14. Next recommended tasks

1. **Creator opt-out column (Data track)** — it is the one thing standing between the Passport and being usable, and it is small.
2. **`payment_status` table (Data track, D-027)** — the largest blocker on the board; five separate features wait behind it.
3. **Settle the three open decisions** — media storage, job runner, and who the pilot serves. Each is blocking real work.

_Not started automatically. Awaiting founder approval._

## 15. Handoff

- **Pick up from:** `feature/creator-passport`, last commit `4d8d91c`, pushed.
- **Pending:** PR not opened. Nothing uncommitted.
- **Open questions:** Should the Passport show `member_since` at all? It is coarse (`2026-09`) by design, but it is still a signal about the creator.
- **Watch out for:**
  - `requirements.txt` changed. Run `pip install -r requirements.txt` or your environment will disagree with the repo.
  - `requirements.txt` is a shared file (CLAUDE.md section 1) — Erode Harish needs telling, which this report does.
  - CI now fails on any known dependency vulnerability. If it goes red on a package we cannot fix yet, the answer is `--ignore-vuln <ID>` with a comment naming who decided and why — never removing the gate.
  - The body-limit middleware sits **inside** the rate limiter on purpose. Moving it outside would let oversized requests escape the rate limit.
- **First command to run:** `pip install -r requirements.txt`
