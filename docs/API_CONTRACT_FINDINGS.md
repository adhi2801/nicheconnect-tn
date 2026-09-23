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

**Where the count stands.** 48 findings on the first run, 8 now: three fixes,
each one root cause. What is left is the `Allow` header (7) and one correct
refusal (1), both below.

**Not gated yet:** everything below. They are real, and turning them on before
they are fixed would make CI red on day one, which teaches everyone to ignore
it. Each needs its own branch and its own review.

---

## Fixed already

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

## Open

### 1. `Allow` header on a 405 is incomplete (7–8 findings)

An `OPTIONS` request to a path with several methods returns 405 with an
`Allow` header listing only the methods of the route that happened to match,
not every method the resource supports. Example: `OPTIONS
/api/v1/brands/me` answers 405 with `Allow` missing `GET` and `PATCH`.

RFC 9110 requires `Allow` on a 405 to list every method the resource
supports.

**Why this is not a quick fix.** `OPTIONS` is also the CORS preflight verb.
D-044 put the CORS layer deliberately outside the rate limiter and relies on
today's `OPTIONS` behaviour, and D-045 settled which headers an error answer
carries. Changing 405 handling touches both. It needs its own branch, and the
CORS preflight tests must still pass.

**Who:** API track. **Needs:** a decision on whether to answer `OPTIONS`
properly per resource, or to keep 405 and only correct the header.

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

The one remaining finding in this class is a valid OTP-shaped code that is not
the real one, answered with 400. That is correct behaviour and belongs to
finding 2 below: 400 is simply not documented for that operation.

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
