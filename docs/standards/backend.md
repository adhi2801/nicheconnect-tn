# Backend Standard

**For:** anyone writing endpoints, services, schemas or background jobs under `app/`, read before the first file (`CLAUDE.md` section 6). **Last checked against the code: 14 October 2026**, on branch `docs/standards-bar`. Every claim below was re-checked then. Three that had stopped being true were corrected; they are listed in section 12. **Section 0 added 6 November 2026**, each of its "Today" cells checked against the code that day.

**The bar** is `CLAUDE.md` section 7.0: the best published practice, from Stripe's API, Google's API Improvement Proposals, Zalando's RESTful API guidelines and the IETF RFCs (sources in section 13), proven by tests rather than claimed. Each rule says what **enforces** it. A rule nothing enforces is marked *(review only)*, so the difference between a checked rule and a hope stays visible.

Rules marked **(decision)** need a founder decision in `docs/DECISIONS.md` before first use. Rules marked **(not yet used)** apply the first time the situation arises.

**The twelve dimensions** (`CLAUDE.md` section 5, D-139), and where this standard serves each:

| Dimension | Here |
|---|---|
| Quality | Every rule names its enforcement; sections 2 to 6 |
| Architecture | Layers and module layout, section 1 |
| Security | Errors that leak nothing (3), validation (4), locks (5); the full rules are `security.md` |
| Privacy and law | What logs and traces may hold, section 9; consent and data rules are `legal.md` |
| Trust and safety | Not here: `trust-and-safety.md` |
| Performance | Budgets, query counts, overload, section 6 |
| Design | One error shape the screens can show, at most two calls a screen (sections 2, 3, 6) |
| Research | Section 13 |
| Novelty | None claimed: this is engineering practice. Our edge it serves is facts worked out, never stored (section 2) |
| Business | A stable contract the website and both apps build against (section 2) |
| Reliability | Overload, timeouts and retries (section 6), jobs that finish or resume (section 7), the availability target and its error budget (section 0) |
| Maintainability | Layers (section 1), one way to do each thing (sections 2 to 5), a contract that never breaks (section 0) |

---

## 0. The benchmarks we beat (Adhi, 6 November 2026: "backend too need to beat the global biggest ones ... sky high")

The frontend names Stripe, Linear, Vercel and Apple as its bar (`frontend.md` section 8a). The backend's bar is the same companies' engineering, as they publish it. Each row gives what the leader commits to, with its source; our bar, a number wherever one can be measured; what enforces it; and whether it holds today. A row marked **(decision)** proposes a number that binds only once a founder approves it.

| Benchmark | What the leader publishes | Our bar | Enforced by | Today |
|---|---|---|---|---|
| **Never breaking a client** (Stripe) | Compatibility kept with every API version since 2011; versions named by date; changes packaged so old versions keep working ([Stripe, "APIs as infrastructure", 5 August 2017](https://stripe.com/blog/api-versioning)) | A published field, route or error code is never removed or changed in meaning. A breaking need gets a new route, and the old one a `Deprecation` and a `Sunset` date (RFC 9745, RFC 8594) at least **12 months** ahead **(approved, D-179)** | The committed contract (`tests/test_api_contract.py`) shows every change; an automatic breaking-change check on the contract in CI **(approved, D-179; the tool is a dependency)** | Additive only so far; the automatic check does not exist |
| **Safe retries** (Stripe; IETF) | Idempotency keys on every POST, the first answer replayed ([Stripe docs](https://docs.stripe.com/api/idempotent_requests)) | Every write a person can repeat by tapping twice takes an `Idempotency-Key` and replays its first answer (draft-ietf-httpapi-idempotency-key-header-07) | `tests/core/test_idempotency.py` and each route's idempotency test | **Holds** |
| **Availability** (Stripe; Google SRE) | Stripe's API stayed above **99.999%** through the 2023 Black Friday peak of 27,395 requests a second ([Stripe newsroom, 2023](https://stripe.com/newsroom/news/bfcm2023)). Google SRE: never a 100% target; an error budget, "a rate at which the SLOs can be missed"; "start with a loose target that you tighten" ([SRE book, "Service Level Objectives"](https://sre.google/sre-book/service-level-objectives/)) | **99.9%** of requests answered without a 5xx, monthly, through the pilot; **99.95%** from launch (**approved, D-166**). A spent budget stops feature work until it is earned back | A synthetic check and the 5xx rate from traces, alerting at half the budget **(decision: hosting, items 88 and 89)** | No target was written down until now; the overload rule (section 6) already turns a freeze into a quick 503 |
| **The tail, not the average** (Google SRE) | "a high-order percentile, such as the 99th or 99.9th, shows you a plausible worst-case value" (same chapter) | p95 at most 300 ms for reads and 500 ms for writes (section 6), and now **p99 at most 800 ms for reads and 1,200 ms for writes** at pilot scale **(approved, D-179)** | `scripts/measure_performance.py` and `scripts/load_test.py`, their numbers in `docs/PERFORMANCE.md` | p95 measured per route; p99 not yet a gate |
| **Telling a client its limits** (GitHub; IETF) | GitHub sends `x-ratelimit-limit`, `-remaining`, `-used`, `-reset` and `-resource` on every response ([GitHub REST docs](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)); the IETF's `RateLimit` and `RateLimit-Policy` fields are a standards-track draft, version 11 of May 2026 ([IETF](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers-11)) | Every rate-limited response carries the draft's `RateLimit-Policy` and `RateLimit`, as idempotency already follows its own draft; `Retry-After` stays on every 429 **(approved, D-179)** | A test over every route's headers | `Retry-After` on 429 only |
| **Security verified, not assumed** (OWASP) | ASVS 5.0.0, published 30 May 2025 ([OWASP ASVS](https://asvs.owasp.org/)) | **Level 2** on every route; **Level 3** on login, tokens, account deletion, payment status and the admin API (**approved, D-166**); each requirement mapped to the test or file that meets it, re-checked every release | A requirement map in `docs/standards/security.md`, its gaps listed there | The OWASP API Security Top 10 (2023) is the bar today (section 13) |
| **A build anyone can verify** (SLSA) | SLSA build levels: L1, provenance exists; L2, a hosted platform signs it; L3, a hardened platform keeps the signing secrets from build steps (version 1.2 is current; [SLSA v1.1 levels](https://slsa.dev/spec/v1.1/levels)) | **SLSA Build L2** for the API image now (provenance signed by GitHub Actions), **L3** before launch (**approved, D-166**) | The release job, and a verification step before every deploy | A CycloneDX SBOM per image (D-082); no signed provenance |
| **Proven by breaking it** | Beyond what the leaders publish | Every rule shown to fail when broken; mutation testing on every rule where a silent mistake costs money or trust, its survivors falling every release (`testing.md` section 2) | The nightly mutation run and its floor (D-139) | **Holds**, its survivors named |

What moves a row from **(decision)** to binding: a founder's yes, recorded in `docs/DECISIONS.md` (`CLAUDE.md` section 5), with its enforcement built in the same change.

---

## 1. Architecture: layers and module layout

**Layers** (D-099). A module imports only from layers below it:

| Layer | Modules | What lives there |
|---|---|---|
| 7 | `me` | Views of one account that read every module: attention, the data export; and the two account actions that need modules above `auth`: asking for a step-up code (it checks a UPI ID by `payment_status`'s rule) and logging out everywhere (its alert needs `notifications`), item 82; and changing the phone number, with its job (its alerts too), item 80; and listing sessions and ending one (its alert too), item 81; and deleting the account, with its job, which reaches every module, item 6 |
| 6 | `admin` | The admin API and its log, the founders' numbers, user reports |
| 5 | `matching` \| `insights` \| `passport` | Who fits whom and creator search; anonymous market figures; how a creator is shown |
| 4 | `campaigns` : `deal_memo` : `payment_status` : `disputes` | The deal domain. `:` lets them import each other until item 96 untangles them |
| 3 | `profiles` \| `safety` \| `notifications` | What people say about themselves; blocking; in-app notifications |
| 2 | `auth` | Login, tokens, sessions, devices, attribution, suspension, access checks, the identity tables |
| 1 | `app/core`, `app/db` | Never import a module, except the two registries named in `pyproject.toml` |

- `|` keeps siblings independent. Something two layers need moves down, never sideways.
- Where a piece belongs is decided by what it imports, not what it is named after. The Passport shows deal records, so it sits above the deal domain.
- A new module is placed in a layer before it is built.
- **Enforced by** `lint-imports` in CI: it fails on an upward import and on a module placed in no layer. `tests/test_architecture.py` fails on a module folder without `__init__.py`, which would hide it from the check.

**Module layout.** Each module under `app/modules/<name>/` owns its files:

| File | Job | May import |
|---|---|---|
| `<feature>_router.py` | HTTP only: parse, call the service, return a schema | its services and schemas, `auth.dependencies`, `app/core` |
| `schemas.py` | Pydantic request and response shapes | its own models' constants, and lower layers' schemas |
| `<feature>_service.py` | Business rules and transactions | models, schemas, `app/core`, lower modules' services |
| `models.py`, `models/` or `<feature>_models.py` | SQLAlchemy tables | `app/db` |
| `dependencies.py` | FastAPI dependencies: the current account, ownership loaders | services, `app/core` |
| `exceptions.py` | The module's domain errors | `app/core/errors` |

- Routers never touch the database; services never import FastAPI. **Enforced by** `tests/test_architecture.py`, which fails when a router builds a query (`select`, `insert`, `update`, `delete`, `text`) or a service imports FastAPI or Starlette.
- A module reaches another through its service, never its router. A join may read another module's models; nothing writes them. *(review only)*
- One file, one job: a new feature gets its own `<feature>_router.py` and `<feature>_service.py`, rather than swelling the main ones. *(review only)*

## 2. API design

- **Base path** `/api/v1`. Resources are plural nouns (`/campaigns/{campaign_id}/applications`). An action that is not create, read, update or delete takes a verb sub-path (`POST /deal-memos/{id}/accept`, following Google's custom methods, AIP-136). The signed-in person's own things live under `/me/...`, with no id in the path, so nobody can reach anyone else's.
- **JSON fields** are `snake_case`. IDs are UUID strings. Timestamps are RFC 3339, in UTC, ending in `Z`. Dates (`…_on`) are `YYYY-MM-DD`, and a day means a Tamil Nadu calendar day: a date is taken from a moment only through `app.core.clock.india_date`, and a deadline that ends with a day is given to clients as the instant it ends (`end_of_india_day`, as Google's AIP-142 gives one). **Enforced by** `tests/test_architecture.py::test_every_date_from_a_moment_is_a_tamil_nadu_day` (D-180).
- **Money** is whole paise as integers with an explicit currency (D-015), never floats: `{"amount_paise": 1500000, "currency": "INR"}`. **Enforced by** every currency column's database check, and `Literal["INR"]` in the schemas.
- **Status codes** (RFC 9110 semantics):

| Case | Code |
|---|---|
| Read OK | 200 |
| Created | 201, with a `Location` header |
| Accepted for background processing | 202 |
| Deleted, or no body | 204 |
| Not modified (conditional read) | 304 |
| A body that cannot be read at all (not UTF-8) | 400 |
| Validation failed | 422 |
| Not logged in, or a bad token | 401 |
| Logged in but not allowed | 403, or 404 when admitting the object exists would leak it |
| Not found | 404 |
| State conflict: a duplicate, a wrong transition, a lost race | 409 |
| Too large | 413 |
| Rate limited | 429, with `Retry-After` |
| A dependency down, or the process at capacity (`service_busy`, with `Retry-After`, D-093) | 503 |
| Unexpected | 500, with a generic message only |

- **Pagination** applies to every list that can grow without a bound. It is keyset, newest first (Google AIP-158): `?limit=20&cursor=<opaque>`, default 20, maximum 100, answering `{"items": [...], "next_cursor": "<opaque or null>"}`. Never page numbers or offsets, which skip and repeat rows while data changes.
  - A list a rule bounds may come whole, and its description states the bound: at most 10 packages (D-055), 20 files a proof, 5 admin search results, sign-ups by source over the weeks asked for.
  - A document is one response: the campaign report, a deal's record. The data export, which grows with an account's whole history, is built by a job and downloaded once (D-111).
  - **Enforced by** a query-count test on every paginated list, proving a long page costs the same queries as a short one (`docs/PERFORMANCE.md`). That a new list is paginated at all is *(review only)*.
- **Filtering** uses explicit, allow-listed query parameters; unknown or malformed values get 422. **Enforced by** FastAPI's parameter validation, and Schemathesis fuzzing every operation.
- **A change to part of an object** (`PATCH`) changes only the fields sent; sending none is a 422. Null clears a field only where the column may be empty: for one that always holds a value, the schema refuses null with `value_required` (`check_change` in `app/core/partial_update.py`), and any rule across fields is checked on the object as it would be after the change, not on the fields sent (a campaign's budget, `campaigns/budget.py`). Before 7 November four schemas let null, and a budget change, through to the database's own checks, answered 500 (audit C6). **Enforced by** `tests/test_update_schemas.py`, which holds every `*Update` schema to its table's NOT NULL columns and fails on a schema it does not list.
- **Idempotency** (Stripe's `Idempotency-Key`; D-040): every `POST` and `PATCH` outside `/api/v1/auth/` accepts the header, through `route_class=IdempotentRoute`, and a repeated key returns the original response. One exception, by design: downloading a data export, whose answer is a person's whole file and must not be kept in the idempotency store (D-111). `PUT` replaces a whole object and is idempotent by nature. **Enforced by** `tests/modules/test_retry_safety_api.py::test_every_write_outside_login_accepts_an_idempotency_key`, which names the exception and its reason.
- **Worked out, never stored.** Anything that follows from stored facts is computed at read time against an injected `now`: a payment's state, a deal's stage, Complete, a delivery record, the campaign report. A stored copy of a derived fact is a second truth that drifts. *(review only)*, backed by each rule's pure tests.
- **Null means "not enough to say".** Where a figure rests on too few examples it is `null`, never `0`, and the response says how many examples there were (D-027, D-038, D-056). **Enforced by** threshold tests for city figures, fair-rate guidance, response times and the founders' numbers; for the others, *(review only)*.
- **Conditional reads** on public, cacheable answers carry `Cache-Control` with a stated time to live, and an `ETag` hashed from the body; `If-None-Match` gets 304 (the Passport, city figures, festival templates), compared as RFC 9110 section 13.1.2 says: weakly, against a list, `*` included, so a proxy that marks the tag weak while compressing still gets its 304 (`app/core/http_cache.py`; exact comparison until audit C7, 7 November 2026). **Enforced by** `tests/core/test_http_cache_properties.py` and the Passport's API tests.
- **Evolving the API** (Zalando's compatibility rules):
  - Within `v1`, changes are only additive: new endpoints, new optional request fields, new response fields.
  - Clients ignore unknown response fields and tolerate enum values they do not know; each list of values says so.
  - Removing or renaming anything, or tightening validation, is breaking. It needs a decision and a deprecation period, announced with `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) **(not yet used)**.
- **OpenAPI is the contract.**
  - Every route has a `summary`, a `description`, a response shape, documented errors, and examples on non-obvious fields.
  - The committed copy is `docs/api/openapi.json`. Refresh it with `uv run python -m tests.openapi_snapshot` and commit it with the change, so every contract change is a visible diff.
  - **Enforced by** `tests/test_api_contract.py`:
    - the running app matches the committed copy;
    - every operation needs a login unless it is on a named public list;
    - 401, 422, 429, 400 and the 503 "busy" answer are documented where they apply;
    - every error uses the one format;
    - every success has a documented shape.
  - CI fuzzes every operation against the contract (Schemathesis).

## 3. Errors

One shape for every non-2xx answer, RFC 9457 Problem Details:

```json
{
  "type": "https://nicheconnect.in/errors/campaign-not-open",
  "title": "Campaign is not open for applications",
  "status": 409,
  "detail": "Campaign 3f2a… is closed.",
  "code": "campaign_not_open",
  "request_id": "01J…",
  "errors": [{"field": "pitch", "message": "Must be 20–1000 characters"}]
}
```

- `code` is stable and machine-readable; clients branch on it, never on `title` or `detail`. A `code` is never renamed.
- Services raise domain exceptions (`CampaignNotOpen`), and one global handler turns them into Problem Details. Routers never build error JSON. **Enforced by** the contract test's one-error-format check.
- Every error answer, a 500 and a 503 included, carries the same security headers, CORS headers and request ID as a success (D-045). **Enforced by** the error-middleware tests (`tests/core/test_unexpected_error.py`, `tests/core/test_load_shedding.py`).
- Never leak a stack trace, SQL, another person's internal ID, or whether a phone number exists.
- Messages are human-readable, say how to fix the problem, and are safe to show (`ux.md` section 6). *(review only)*
- A race lost to another request is a clean 409 with its own `code`, never a 500. **Enforced by** each rule's concurrency test (`testing.md` section 4).

## 4. Validation and schemas

- A schema per direction: `CampaignCreate`, `CampaignUpdate`, `CampaignRead`. Never return an ORM object, or reuse an input shape for output.
- Every request body refuses unknown fields (`extra="forbid"`), which blocks mass assignment (OWASP API3:2023). **Enforced by** `tests/test_architecture.py::test_every_request_body_refuses_unknown_fields`, across all 39 body shapes, with a guard that fails if it ever finds none.
- Constrain every field: lengths, ranges, `Literal` enums, patterns for handles and codes, UUID types. Strip whitespace; lowercase emails.
- Every `Literal` that mirrors a database allow-list is tied to it with `ensure_same_values`. **Enforced at startup**: the app refuses to start if they differ.
- Server-controlled fields (`id`, owner ids, `status`, timestamps) never appear in create or update shapes.
- Phone numbers are validated and stored in E.164 (`+91XXXXXXXXXX`). **Enforced by** the database check and property tests (D-090).
- Public responses are built field by field, never dumped from a model, so a column added later cannot leak. *(review only)*

## 5. Services, transactions and concurrency

- One service call is one unit of work and one transaction, committed in one place per request.
- State changes go through an explicit transition table. Illegal transitions raise a 409 domain error, each with a test.
- **Check, then write, never without a lock.** A rule like "only if still open", "at most ten" or "not already decided" is checked after locking the row it depends on, in the same transaction:
  - `db.refresh(obj, attribute_names=[...], with_for_update=True)` for the attributes the check reads;
  - or `select(...).with_for_update().execution_options(populate_existing=True)`.

  A unique-constraint violation is caught and answered as 409. "Insert or update" is one `INSERT … ON CONFLICT`. **Enforced by** a concurrency test for each such rule (`testing.md` section 4), and nightly mutation testing removing locks (D-091). This is the pattern behind every race fixed on 4 October (`docs/REVIEW_FINDINGS.md`).
- Side effects (notifications, external calls) happen after commit or in a background job, never inside the transaction.

## 6. Performance and overload

- Routes are synchronous (`def`) with the synchronous SQLAlchemy session; no `async` database access. Async is scaling proposal S1 in `docs/ARCHITECTURE_SCALE.md`, with the measured trigger that would justify it.
- **Budgets** at pilot scale, with seeded data: p95 ≤ 300 ms for reads, ≤ 500 ms for writes, measured (`docs/PERFORMANCE.md`). Anything over budget is investigated before merge.
- **A fixed number of queries per request**, whatever the page size: related rows load in one query per kind (`IN (...)`, a join, or `selectinload`). **Enforced by** a query-count test on every list, each shown failing when a per-row query is added.
- A screen needs at most two calls; more is a backend request (`ux.md` section 7).
- External calls (WhatsApp, the Claude API, SMS, timestamp authorities, the trace exporter): explicit timeouts (connect 3 s, read 10 s; traces 3 s), retry with exponential backoff and jitter (at most 3 attempts), and never inside a request a person waits on.
- Cache only with a written reason, a time to live, and an invalidation rule.
- **Overload is a quick 503, never a freeze** (D-093, after Google SRE's "Handling Overload"):
  - `app/core/load_shedding.py` admits at most `MAX_IN_FLIGHT_REQUESTS` at once, fewer than the pool's connections, so an admitted request can always get one;
  - a request finding no place within `BUSY_QUEUE_MS` gets 503 `service_busy` with `Retry-After`, as does one waiting longer than `DB_POOL_TIMEOUT_SECONDS` for a connection;
  - health checks are never held back;
  - **enforced** at startup (a cap that could use every connection stops the app), by `tests/core/test_load_shedding.py`, and by `scripts/load_test.py --overload`.

## 7. Background jobs

- DBOS runs them (D-060): durable workflows whose state lives in Postgres, with no broker and no extra service.
- Jobs are idempotent: running one twice is safe, and a test proves it.
- Every job logs its start, success or failure with its id. Failed jobs retry with backoff, then land in a failed state someone can see: the data export tries 3 runs a minute apart, then is marked failed and its owner told (D-112).
- A job that spends money (the Claude API) has a daily ceiling in settings (D-070).

## 8. Configuration

- Every setting comes from environment variables through `app/core/config.py` (pydantic-settings), as the Twelve-Factor App's config factor sets out. **Enforced by** `tests/test_architecture.py::test_settings_are_read_only_through_config`, which fails on `os.getenv` or `os.environ` anywhere else.
- The app refuses to start if a setting is missing, malformed, unsafe or still a placeholder, with a message naming the fix. **Enforced by** `tests/core/test_config.py`.
- `.env.example` lists every setting with a safe placeholder and a one-line comment. **Enforced by** `tests/core/test_config.py`.
- **Infra passes every setting that must differ by environment.** The rest run on the code's defaults. On 14 October, 13 of 36 settings were not passed (the three added that day, for the app's own database login and the log format, are), among them the pool and overload settings and `TRACES_ENDPOINT` (section 12).

## 9. Logging and observability

- Every request gets a `request_id`, from `X-Request-ID` or generated. It is returned in the response header and included in every log line and error body.
- **Log events, not data:** `campaign.created campaign_id=…`. **Never log** phone numbers, emails, codes, tokens, bank or UPI details, or request bodies. Log an exception's type, not its message, when the message could hold them. *(review only)* for what each log call writes; the JSON lines' redaction and the Sentry scrubber are tested.
- **Tracing** (OpenTelemetry, D-094; W3C Trace Context):
  - one span per request, named by its route template, with a child span per database query, continuing an incoming `traceparent`;
  - on only when `TRACES_ENDPOINT` is set;
  - a span carries the method, route template, status, request ID and error type, and SQL with placeholders. Never a real path, query string, header, body, account, address or exception message;
  - health probes are not traced;
  - **enforced by** `tests/core/test_tracing.py`, which reads spans exactly as they would be sent.
- `/healthz` answers "is the process up". `/readyz` checks the database and Valkey with short timeouts, and answers 503 when either is down.
- Errors go to Sentry (D-074), scrubbed of personal data before they leave the process. **Enforced by** tests that read exactly what would be sent, including property tests on phone numbers.
- **Structured logs** (D-102): with `LOG_FORMAT=json`, which infra sets, every line, Uvicorn's included, is one JSON object: time in UTC, level, logger, event, `request_id` and `trace_id`. The event and an exception's stack pass through the same redaction as error reports; an exception logs its type and stack, never its message; an access line keeps method, path and status, never the client's address or the query string. **Enforced by** `tests/core/test_structured_logs.py`, which reads the lines exactly as written, including a property test that no mobile number survives.

## 10. Code style

- Python 3.14, installed and pinned by uv (D-072). Type hints on every signature. **Enforced by** mypy strict on `app/` and ruff for format and lint (D-037), in CI.
- Functions do one thing; about 40 lines is a smell worth questioning. *(review only)*
- Names say what things are: `get_open_campaigns_for_brand`, not `get_data`. *(review only)*
- Every module and every public service function has a docstring: what it does, why it is built this way, and what it raises. The *why* matters most; nobody should have to rediscover a decision. *(review only)*
- No commented-out code, no `print`, no `assert` in `app/` (it vanishes under `-O`), and no `TODO` without a linked item. Checked by search on 14 October: none present. *(review only)*

## 11. How this file is kept true

- Re-checked against the code whenever it is read for work, and at least monthly with `docs/PLATFORM_AND_TECH_PLAN.md`'s review.
- A rule that gains enforcement says so. A rule found untrue is corrected in the same change, never left to mislead (`docs/README.md` section 0).

## 12. Gaps, named

| Gap | Risk | Acting on it |
|---|---|---|
| **13 of 36 settings not passed by infra**, among them `TRACES_ENDPOINT`, `DB_POOL_SIZE`, `MAX_IN_FLIGHT_REQUESTS` and `BUSY_QUEUE_MS`. The rule said "infra passes every one" until 14 October. | Production cannot turn tracing on, or tune capacity, without an infra change | Items 88 and 89; passing them is an infrastructure decision |
| **Error `type` URLs are on `nicheconnect.in`**, a domain we do not own | A public contract pointing at someone else's domain | Item 4: the name and the domain decide it, before any client exists |
| **The list of proofs on a deal has no cap** | Tiny in practice; unbounded in principle | Cap resubmissions, or paginate, when proof volume says so |
| **The deal domain still imports across itself** | Changes there ripple further than they should | Item 96 |
| **`Deprecation` and `Sunset` never used** | None yet: nothing has been removed | Applies at the first breaking change |
| Several rules are *(review only)* | They hold only while someone reads for them | Each gains a test when one is practical; two gained tests on 14 October |

## 13. Sources

Each link checked to exist on 14 October 2026.

- Problem Details: [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457). HTTP semantics: [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110). Timestamps: [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339). Deprecation and sunset: [RFC 9745](https://www.rfc-editor.org/rfc/rfc9745), [RFC 8594](https://www.rfc-editor.org/rfc/rfc8594).
- Google API Improvement Proposals: [AIP-158 pagination](https://google.aip.dev/158), [AIP-193 errors](https://google.aip.dev/193), [AIP-180 backwards compatibility](https://google.aip.dev/180).
- [Zalando RESTful API guidelines](https://opensource.zalando.com/restful-api-guidelines/): compatibility and evolution.
- [Google AIP-136: custom methods](https://google.aip.dev/136).
- [Stripe: idempotent requests](https://docs.stripe.com/api/idempotent_requests).
- [OWASP API Security Top 10, 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/): mass assignment (API3) and the rest.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) and [OpenTelemetry HTTP span conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/).
- [Google SRE book: Handling Overload](https://sre.google/sre-book/handling-overload/), and [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) (read 6 November 2026).
- Section 0, read 6 November 2026: [Stripe, "APIs as infrastructure"](https://stripe.com/blog/api-versioning) (5 August 2017); [Stripe newsroom, Black Friday and Cyber Monday 2023](https://stripe.com/newsroom/news/bfcm2023); [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api); [IETF RateLimit header fields, draft 11](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers-11); [OWASP ASVS 5.0.0](https://asvs.owasp.org/); [SLSA build levels](https://slsa.dev/spec/v1.1/levels).
- [The Twelve-Factor App: config](https://12factor.net/config).
- [DBOS documentation](https://docs.dbos.dev/).
- Module boundaries: Shopify's Packwerk and GitLab's modular monolith design, as cited in D-099.
