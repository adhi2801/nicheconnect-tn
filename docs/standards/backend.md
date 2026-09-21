# Backend Standard

Applies to everything under `app/`. Read before writing endpoints, services, schemas or jobs.
Rules marked **(decision)** need a founder decision recorded in `docs/DECISIONS.md` before first use.

---

## 1. Module layout

Each module under `app/modules/<name>/` owns its own files:

| File | Job | May import |
|---|---|---|
| `router.py` | HTTP only: parse the request, call the service, return a schema | `service`, `schemas`, `app/core` |
| `schemas.py` | Pydantic request/response models | nothing app-specific |
| `service.py` | Business rules and transactions | `models`, `schemas`, `app/core`, other modules' **services** |
| `models.py` (or `models/`) | SQLAlchemy tables | `app/db` |
| `dependencies.py` | FastAPI dependencies (current user, ownership loaders) | `service`, `app/core` |
| `exceptions.py` | Domain errors for this module | nothing |

- Routers never touch the database directly. Services never import FastAPI.
- A module never imports another module's `models` or `router`. It goes through that module's `service`.
- No circular imports. If two modules need each other, the shared piece moves to `app/core` (ask first).

## 2. API design

- **Base path:** `/api/v1`. Breaking changes need a new version, never an in-place change.
- **Resources are plural nouns:** `/campaigns`, `/campaigns/{campaign_id}/applications`. Actions that aren't CRUD use a verb sub-path: `POST /deal-memos/{id}/accept`.
- **JSON fields:** `snake_case`. IDs are UUID strings. Timestamps are ISO 8601 in UTC with `Z`.
- **Money in the API:** integer amounts in paise with an explicit currency, e.g. `{"amount_paise": 1500000, "currency": "INR"}`. Never floats. **(decision)** confirm before the first money field.
- **Status codes:**

| Case | Code |
|---|---|
| Read OK | 200 |
| Created | 201, plus a `Location` header |
| Accepted for background processing | 202 |
| Deleted / no body | 204 |
| Validation failed | 422 |
| Not logged in / bad token | 401 |
| Logged in but not allowed | 403, or 404 when revealing that the object exists would leak information |
| Not found | 404 |
| State conflict (duplicate, wrong status transition) | 409 |
| Rate limited | 429, plus a `Retry-After` header |
| Unexpected | 500, with a generic message only |

- **Pagination** on every list: cursor-based. Request `?limit=20&cursor=<opaque>`; default limit 20, maximum 100. Response:
  `{"items": [...], "next_cursor": "<opaque or null>"}`
- **Filtering and sorting:** explicit, allow-listed query parameters only (`?status=open&sort=-created_at`). Unknown parameters return 422.
- **Idempotency:** every `POST` and `PATCH` outside `/api/v1/auth/` accepts an `Idempotency-Key` header, by building its router with `route_class=IdempotentRoute` (D-040). A repeated key returns the original response. A test fails if any new write is missing it. Login is excluded until decided separately.
- **OpenAPI is the contract.** Every route has a `summary`, a `response_model`, documented error responses and request/response examples. `/docs` must stay accurate enough for the future frontend to build against. A committed copy lives in `docs/api/openapi.json`, and `tests/test_api_contract.py` fails when the running app differs from it. When a change is intended, refresh it with `venv\Scripts\python.exe -m tests.openapi_snapshot` and commit it with the change, so every contract change is a visible diff in review. The same test file checks, across every operation: a login is required except on a named public list; every operation has a summary, a description and a documented success shape; 401, 422 and 429 are documented where they apply; and every error is documented as Problem Details.

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

- `code` is a stable machine-readable string; the frontend relies on it.
- Services raise domain exceptions (`CampaignNotOpen`). One global handler maps them to Problem Details. Routers don't build error JSON by hand.
- Never leak stack traces, SQL, internal IDs of other users, or whether an email or phone exists.
- Validation messages are human-readable and safe to show to users.

## 4. Validation and schemas

- Separate schemas per direction: `CampaignCreate`, `CampaignUpdate`, `CampaignRead`. Never return ORM objects or reuse input schemas for output.
- Input schemas use `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected (blocks mass assignment).
- Constrain every field: string lengths, numeric ranges, enums, regex for handles, UUID types. Strip whitespace. Normalise emails to lowercase.
- Server-controlled fields (`id`, `owner_id`, `status`, timestamps) never appear in create or update schemas.
- Phone numbers are validated and stored in E.164 format (`+91XXXXXXXXXX`).

## 5. Services and transactions

- One service call = one unit of work = one transaction. Commit happens in one place per request.
- State changes (application status, deal memo status, payment status) go through an explicit transition table. Illegal transitions raise a 409 domain error and have a test each.
- Concurrent updates to the same record use optimistic locking (a `version` column checked on update) where two people can edit the same object. **(decision)** per table.
- Side effects such as notifications happen **after** commit, via a background job, never inside the transaction.

## 6. Async and performance

- **(decision)** sync vs async SQLAlchemy. Whichever is chosen is used everywhere; never mix them in one request path.
- Never call blocking I/O (`requests`, `time.sleep`, CPU-heavy embedding) inside an `async def` route. Use a background job or a thread pool.
- Budgets at pilot scale, with seeded data: **p95 ≤ 300 ms reads, ≤ 500 ms writes**. Any endpoint over budget gets investigated before merge.
- Load related data explicitly (`selectinload`/`joinedload`); a test or query log check guards list endpoints against N+1 queries.
- External calls (WhatsApp, Claude API, SMS): set timeouts (connect 3 s, read 10 s), retry with exponential backoff and jitter (max 3 attempts), and always run in background jobs.
- Cache only with a written reason, a TTL, and an invalidation rule. Cache keys include the API version.

## 7. Background jobs

- **(decision)** job runner (e.g. RQ, ARQ, Celery). Until decided, don't add one.
- Jobs are idempotent: running one twice must be safe.
- Every job logs start, success or failure with `request_id` / `job_id`. Failed jobs retry with backoff, then land in a failed state that someone can see.

## 8. Configuration

- All settings come from environment variables through `app/core/config.py` (pydantic-settings). No `os.getenv` scattered around the code.
- The app refuses to start if a required setting is missing.
- `.env.example` lists every variable with a safe placeholder and a one-line comment.

## 9. Logging and observability

- Structured JSON logs in staging and production; readable logs locally.
- Every request gets a `request_id` (from the `X-Request-ID` header or generated), returned in the response header and included in every log line and error body.
- Log events, not data: `campaign.created campaign_id=… brand_id=…`. **Never log** phone numbers, emails, OTPs, tokens, passwords, bank or UPI details, or full request bodies.
- `/healthz` answers "is the process up"; `/readyz` checks database and Redis connectivity with short timeouts.
- Errors go to Sentry once deployed, with PII scrubbing on.

## 10. Code style

- Python 3.12, type hints on every function signature and return value.
- Formatting and linting: ruff (format + lint). Type checking: mypy in strict mode for `app/`. Adopted in D-037, configured in `pyproject.toml`, and enforced in CI.
- Functions do one thing; about 40 lines is a smell worth questioning.
- Names say what things are: `get_open_campaigns_for_brand`, not `get_data`.
- Docstrings on every public service function: what it does, what it raises.
- No commented-out code, no `print`, no `TODO` without a linked issue.
