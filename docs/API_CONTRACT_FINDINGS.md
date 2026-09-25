# API contract findings

What Schemathesis found when it was first run against the API, 23 September
2026. Schemathesis reads the OpenAPI document the app serves, generates
requests from it, and checks every answer against what the document promises.

Counts vary a little between runs: these are property-based tests with a
random seed, so each run explores different inputs. The classes below are
stable; the exact numbers are not.

**Gated in CI today:** `not_a_server_error` only. On the runs in this session
it passed completely — 6829 generated cases, 6829 passed, across all 64
operations, no 5xx anywhere. That is `CLAUDE.md` section 7's "no unhandled
exception reaches a user", proved rather than assumed.

**Where the count stands.** 48 findings on the first run, **1 now**: four
fixes, each one root cause. The one left is not a bug — a well-formed OTP
that is not the real code, correctly refused with 400. See finding 3.

**Still not gated:** the other checks stay off in CI. They pass now, but they
are property-based and explore different inputs each run, so a red build on a
branch that changed nothing relevant would teach everyone to ignore it.
Turning them on is worth revisiting once the contract has settled.

---

## Fixed, 23 September

Each was one root cause, found by generating requests from our own document.

### The `Idempotency-Key` header was under-described (was 35 findings)

The document declared the header as `minLength: 8, maxLength: 128` but never
said which characters are allowed, while `check_key()` enforces
`^[A-Za-z0-9._:-]{8,128}$`. So a client generating requests from our own
document produced keys we always answered 422 to, on all 35 operations that
accept the header.

Fixed in `app/core/idempotent_route.py`: the published schema now takes its
`pattern` from `KEY_PATTERN`, the rule the code actually enforces, so the
document and the validator cannot drift apart again. That one change took the
findings from 48 to about 14.

---

### ~~1. `Allow` header on a 405 was incomplete~~ — fixed

An `OPTIONS` or other unsupported method on a path with several methods
returned 405 with an `Allow` header naming only the route that happened to
match: `OPTIONS /api/v1/brands/me` said `POST` when `GET` and `PATCH` answer
there too. RFC 9110 wants every method the resource supports, and a client
reading the short list concludes the rest do not exist.

Fixed in `app/core/errors.py`. Two things made it more than a one-liner:

**`app.routes` is not a flat list.** FastAPI wraps every `include_router` in
a router object, so `route.matches(scope)` stops at the wrapper and never
compares the paths inside it. The routes are flattened first.

**A static path matches its parameterised sibling's pattern.**
`/api/v1/campaigns/discover` matches the pattern for
`/api/v1/campaigns/{campaign_id}`, which answers `PATCH`. Taking every
pattern that matched advertised a `PATCH` that path cannot serve — Schemathesis
caught exactly that on the first attempt, complaining about an *undocumented*
method instead of a missing one. Only the routes sharing the first matching
path template count now, which is the order routing itself resolves in.

**CORS was never at risk.** Preflight is answered by the CORS middleware
before routing, so it never reaches the 405 handler. All ten preflight tests
in `tests/core/test_cors.py` still pass, and three new tests in
`tests/core/test_errors.py` cover the plain case, the included-router case
and the static-versus-parameterised case.

### ~~2. Undocumented status codes~~ — fixed

Every one of these was the same thing: a request body that is not valid UTF-8
is refused before any field is read, and answers 400 `bad_request` rather than
the 422 a field error gets. All 22 operations that take a body can answer it,
and none of them said so, so a client generated from this document met a
status it had no branch for.

Fixed in `app/core/openapi.py`, which already existed to correct the document
once for every route, present and future, rather than asking each route to
remember. `document_unreadable_body()` adds the 400 to every operation with a
request body, and never replaces a 400 a route documented for its own reason.

Guarded by three tests in `tests/test_api_contract.py`: that every
body-taking operation documents 400, that an unreadable body really answers
400 in the Problem Details shape, and that a *readable* body which is not JSON
still answers 422 — because 400 is for bytes we cannot read, not for a body we
can read and reject.

### ~~3. Field patterns not published~~ — fixed

`phone` and `code` were declared as plain strings, while the code required a
10-digit Indian mobile number and a 6-digit OTP. This has been fixed in
`app/modules/auth/schemas.py`, and the class went from 3 findings to 1.

**Worth knowing, because the obvious fix does not work.** Setting Pydantic's
`Field(pattern=...)` publishes nothing here. `IndianMobile` has a
`BeforeValidator` that deliberately accepts `98765 43210`, `+91 98765-43210`
and `09876543210` and normalises them, so the accepted input really is wider
than the stored form. Pydantic is right to drop the constraint from the
**validation** schema, which is the one describing a request body; it keeps it
only in the serialization schema, which describes responses. The pattern is
therefore published through `json_schema_extra`, which documents without
constraining. The document ends up stricter than the code, never looser, and
the wider input keeps working.

---

## The one that remains, and why it stays

A well-formed six-digit code that is not the real OTP is answered with 400
`otp_invalid`. Schemathesis counts that as "API rejected schema-compliant
request", because it expects 2xx, 401, 403, 404, 409, 429 or 5xx.

It is correct behaviour and there is nothing to fix. The request *is*
schema-compliant; it is simply wrong, and a guessed code must be refused. The
only way to satisfy the check would be to answer a bad code with 401 instead,
which would be a worse API: 401 means "you are not authenticated", not "that
code is wrong".

---

## Running it yourself

The API must be running. From the repository root, in two terminals:

```powershell
venv\Scripts\python.exe -m uvicorn app.main:app --port 8099
```

```powershell
$env:PYTHONIOENCODING = "utf-8"
venv\Scripts\schemathesis.exe run http://127.0.0.1:8099/openapi.json --max-time 120 --workers 4 --warnings off
```

`PYTHONIOENCODING` is needed on Windows only: the default console encoding
cannot print Schemathesis's output. CI runs on Linux and does not need it.

To run only what CI gates on, add `-c not_a_server_error`.
