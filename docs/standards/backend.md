# Backend Standard

Applies to everything under `app/`. Read before writing endpoints, services, schemas or jobs. The bar is `CLAUDE.md` section 7.0: the best published practice (Stripe's API, Google's API Improvement Proposals, Zalando's RESTful API guidelines, the IETF RFCs cited below), proven by tests rather than claimed.

Rules marked **(decision)** need a founder decision recorded in `docs/DECISIONS.md` before first use. Rules marked **(not yet used)** apply the first time the situation arises.

---

## 1. Module layout

Each module under `app/modules/<name>/` owns its own files:

| File | Job | May import |
|---|---|---|
| `router.py` (or `<feature>_router.py`) | HTTP only: parse the request, call the service, return a schema | `service`, `schemas`, `app/core` |
| `schemas.py` | Pydantic request/response models | constants from its own `models` |
| `service.py` (or `<feature>_service.py`) | Business rules and transactions | `models`, `schemas`, `app/core`, other modules' **services** |
| `models.py` (or `models/`, `<feature>_models.py`) | SQLAlchemy tables | `app/db` |
| `dependencies.py` | FastAPI dependencies (current user, ownership loaders) | `service`, `app/core` |
| `exceptions.py` | Domain errors for this module | `app/core/errors` |

- Routers never touch the database directly. Services never import FastAPI.
- A module reaches another module through its service, never its router. Reading another module's models in a query is allowed when a join needs it; writing them is not.
- No circular imports. If two modules need each other, the shared piece moves to `app/core` (ask first).
- One file, one job (`CLAUDE.md` section 6): a new feature in a module gets its own `<feature>_router.py` and `<feature>_service.py` rather than swelling the main ones.

## 2. API design

- **Base path:** `/api/v1`.
- **Resources are plural nouns:** `/campaigns`, `/campaigns/{campaign_id}/applications`. Actions that aren't CRUD use a verb sub-path: `POST /deal-memos/{id}/accept`. The signed-in person's own things live under `/me/...` with no id in the path, so nobody can reach anyone else's.
- **JSON fields:** `snake_case`. IDs are UUID strings. Timestamps are RFC 3339 in UTC ending in `Z`. Dates (`…_on`) are `YYYY-MM-DD`; a day means a Tamil Nadu calendar day.
- **Money:** whole paise as integers with an explicit currency (D-015): `{"amount_paise": 1500000, "currency": "INR"}`. Never floats.
- **Status codes:**

| Case | Code |
|---|---|
| Read OK | 200 |
| Created | 201, plus a `Location` header |
| Accepted for background processing | 202 |
| Deleted / no body | 204 |
| Not modified (conditional read) | 304 |
| Validation failed | 422 |
| Not logged in / bad token | 401 |
| Logged in but not allowed | 403, or 404 when revealing that the object exists would leak information |
| Not found | 404 |
| State conflict (duplicate, wrong status transition, lost race) | 409 |
| Too large | 413 |
| Rate limited | 429, plus a `Retry-After` header |
| A dependency is down | 503 |
| Unexpected | 500, with a generic message only |

- **Pagination** on every list: cursor-based (keyset), newest first. Request `?limit=20&cursor=<opaque>`; default limit 20, maximum 100. Response: `{"items": [...], "next_cursor": "<opaque or null>"}`. Cursors are opaque; never page numbers or offsets, which skip and repeat rows while data changes.
- **Filtering:** explicit, allow-listed query parameters only. Unknown or malformed values return 422.
- **Idempotency:** every `POST` and `PATCH` outside `/api/v1/auth/` accepts an `Idempotency-Key` header, by building its router with `route_class=IdempotentRoute` (D-040). A repeated key returns the original response. `PUT` replaces a whole object and is idempotent by nature. A test fails if any new write is missing it.
- **Worked out, never stored.** Anything that follows from stored facts (a payment's state, a deal's stage, Complete, a delivery record) is computed at read time from those facts, against an injected `now`. A stored copy of a derived fact is a second truth that will drift.
- **Null means "not enough to say".** Where a figure rests on too few examples, it is `null`, never `0`, and the response says how many examples there were (D-027, D-038, D-056).
- **Conditional reads on public, cacheable answers:** a `Cache-Control` with a stated TTL and an `ETag` hashed from the body; `If-None-Match` gets 304 (the Creator Passport, city figures).
- **Evolving the API** (Zalando's compatibility rules):
  - Within `v1` only **additive** changes: new endpoints, new optional request fields, new response fields.
  - Clients must ignore unknown response fields and tolerate enum values they do not know; each list of values says so in its description.
  - Removing or renaming anything, or tightening validation, is a breaking change. It needs a decision and a deprecation period, announced with the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers **(not yet used)**.
- **OpenAPI is the contract.**
  - Every route has a `summary`, a `description`, a `response_model`, documented error responses, and examples on non-obvious fields.
  - The committed copy is `docs/api/openapi.json`. `tests/test_api_contract.py` fails when the running app differs from it. Refresh it with `uv run python -m tests.openapi_snapshot` and commit it with the change, so every contract change is a visible diff.
  - The same tests check, across every operation:
    - a login is required, except on a named public list;
    - 401, 422 and 429 are documented where they apply;
    - every error is documented as Problem Details.
  - CI fuzzes every operation against this contract (Schemathesis).

## 3. Errors

One error shape for every non-2xx response (RFC 9457 Problem Details):

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

- `code` is a stable machine-readable string; clients branch on it, never on `title` or `detail`. A `code` is never renamed.
- Services raise domain exceptions (`CampaignNotOpen`). One global handler maps them to Problem Details. Routers don't build error JSON by hand.
- Every error response, a 500 included, carries the same security headers, CORS headers and request ID as a success (D-045).
- Never leak stack traces, SQL, internal IDs of other users, or whether a phone number exists.
- Messages are human-readable, say how to fix the problem, and are safe to show to users (`ux.md` section 6).
- A race lost to another request is a clean 409 with its own `code`, never a 500 from a database error.

## 4. Validation and schemas

- Separate schemas per direction: `CampaignCreate`, `CampaignUpdate`, `CampaignRead`. Never return ORM objects or reuse input schemas for output.
- Input schemas use `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected (blocks mass assignment).
- Constrain every field: string lengths, numeric ranges, enums as `Literal`, regex for handles and codes, UUID types. Strip whitespace. Normalise emails to lowercase.
- Every `Literal` that mirrors a database allow-list is tied to it with `ensure_same_values`, so the two cannot drift.
- Server-controlled fields (`id`, owner ids, `status`, timestamps) never appear in create or update schemas.
- Phone numbers are validated and stored in E.164 (`+91XXXXXXXXXX`).
- Public responses are built field by field, never dumped from a model, so a column added later cannot leak.

## 5. Services, transactions and concurrency

- One service call is one unit of work and one transaction. Commit happens in one place per request.
- State changes go through an explicit transition table. Illegal transitions raise a 409 domain error and have a test each.
- **Check, then write, never without a lock.** A rule like "only if still open", "at most ten" or "not already decided" is checked *after* locking the row it depends on, in the same transaction:
  - `db.refresh(obj, attribute_names=[...], with_for_update=True)` for the attributes the check reads;
  - or `select(...).with_for_update().execution_options(populate_existing=True)` with the row fetched.
  
  A unique constraint's violation is caught and answered as 409. "Insert or update" is one `INSERT … ON CONFLICT` statement. Each such rule has a concurrency test (`testing.md` section 4). This is the pattern behind every race fixed on 4 October (`docs/REVIEW_FINDINGS.md`).
- Side effects (notifications, external calls) happen after commit, or in a background job, never inside the transaction.

## 6. Performance

- Routes are synchronous (`def`) with the synchronous SQLAlchemy session, everywhere; never mix in `async` database access.
- Budgets at pilot scale, with seeded data: **p95 ≤ 300 ms reads, ≤ 500 ms writes**, measured (`docs/PERFORMANCE.md`). Any endpoint over budget is investigated before merge.
- **A fixed number of queries per request, whatever the page size.** Related rows are loaded in one query per kind (`IN (...)`, a join, or `selectinload`), never one per row. Every list endpoint has a test proving a long page costs the same queries as a short one, and that test is shown to fail when a per-row query is added.
- A screen needs at most two calls; more is a backend request (`ux.md` section 7).
- External calls (WhatsApp, Claude API, SMS, timestamp authorities): explicit timeouts (connect 3 s, read 10 s), retry with exponential backoff and jitter (at most 3 attempts), and never inside a request a user waits on: they run in background jobs.
- Cache only with a written reason, a TTL and an invalidation rule.

## 7. Background jobs

- DBOS runs them (D-060): durable workflows whose state lives in Postgres; no broker, no extra service.
- Jobs are idempotent: running one twice is safe, and a test proves it.
- Every job logs start, success or failure with its id. Failed jobs retry with backoff, then land in a failed state someone can see.
- A job that spends money (the Claude API) has a daily ceiling in settings (D-070).

## 8. Configuration

- All settings come from environment variables through `app/core/config.py` (pydantic-settings). No `os.getenv` anywhere else.
- The app refuses to start if a setting is missing, malformed or still a placeholder, with a message naming the fix.
- `.env.example` lists every variable with a safe placeholder and a one-line comment; infra passes every one (`infra/`).

## 9. Logging and observability

- Structured logs in staging and production; readable logs locally.
- Every request gets a `request_id` (from `X-Request-ID` or generated), returned in the response header and included in every log line and error body. W3C `traceparent` propagation arrives with tracing (item 3 in `docs/BACKEND_COMPLETE.md`) **(not yet used)**.
- Log events, not data: `campaign.created campaign_id=…`. **Never log** phone numbers, emails, codes, tokens, bank or UPI details, or request bodies; log an exception's type, not its message, when the message could hold them.
- `/healthz` answers "is the process up"; `/readyz` checks the database and Valkey with short timeouts and answers 503 when either is down.
- Errors go to Sentry (D-074): every error log line, scrubbed of personal data before it leaves the process; tests read exactly what would be sent.

## 10. Code style

- Python 3.14, installed and pinned by uv (D-072). Type hints on every signature; mypy strict on `app/`; ruff for format and lint (D-037), all enforced in CI.
- Functions do one thing; about 40 lines is a smell worth questioning.
- Names say what things are: `get_open_campaigns_for_brand`, not `get_data`.
- Every module and every public service function has a docstring: what it does, why it is built this way, and what it raises. The *why* matters most; a reader should never have to rediscover a decision.
- No commented-out code, no `print`, no `assert` in `app/` (it vanishes under `-O`), no `TODO` without a linked item.
