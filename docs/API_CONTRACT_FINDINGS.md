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

### 2. Undocumented status codes (3–8 findings)

Some operations answer with a status the document does not list for them. The
document is what the frontend will generate its client from, so a status it
does not know about becomes an unhandled branch in the app.

**Who:** API track, alongside the response-documentation work in
`docs/standards/backend.md`.

### 3. Field patterns not published, the same class as the fixed one (3 findings)

`phone` and `code` are declared as plain strings, but the code requires a
10-digit Indian mobile number and a 6-digit OTP. A client building a request
from the document gets 422 on data the document called valid.

Seen on `POST /api/v1/auth/otp/verify`:

- `{"field": "phone", "message": "Enter a valid 10-digit Indian mobile number"}`
- `{"field": "code", "message": "Enter the 6-digit code we sent you"}`

The fix is the same shape as the `Idempotency-Key` one: publish the pattern
the validator already enforces, from one source, so the two cannot disagree.
It changes the public contract, so it is its own change with its own review.

**Who:** API track.

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
