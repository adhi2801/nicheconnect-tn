# Decision needed: how a developer logs in on a laptop

**Status: decided (D-059): option A, built.** Written 26 September 2026.

## The problem

**Nobody can log in to the API on a laptop.** Locally, a login code is
"sent" by the fake sender, which keeps it in a list inside the running
server's memory (`app/modules/auth/sender.py`). Codes are never logged, by
design (`backend.md` section 9), so there is no way to read one. The test
suite reaches into that list directly; a person using the API cannot.

Today that costs a developer ten minutes of workaround. Once design and
frontend work start (D-053), it stops everyone: every screen that needs a
signed-in brand or creator needs a token. It is listed as open in the
backlog's section 4.

It touches authentication, so it is an approval gate (`CLAUDE.md` section 5).

## Options

```
DECISION NEEDED: local login

Option A: a command that prints a token, local only
  venv\Scripts\python.exe scripts\dev_login.py +919000000001
  prints an access token for that account, and refuses to run unless
  ENVIRONMENT=local, the same guard the seed script uses.
  | + no network surface at all: nothing in the running app changes, so a
  |   mistaken setting on a server cannot expose it
  | + works with the seeded accounts straight away
  | − skips the login flow, so it does not exercise OTP itself (the tests do)
  | effort S

Option B: a fixed code, accepted only when ENVIRONMENT=local
  | + a developer goes through the real login screens
  | − a login bypass inside the running app; if a server were ever started
  |   with ENVIRONMENT=local, anyone could sign in as anyone
  | effort S

Option C: a local-only endpoint that returns the last code for a phone
  | + real flow end to end, useful for the frontend later
  | − the same risk as B, and a new route to keep out of production docs
  | effort S

Option D: log the code to the console in local only
  | − breaks the rule that codes are never logged; a log line is the easiest
  |   thing to copy somewhere it should not go
  | effort S

Recommended: A now. It gives everyone a token today with nothing added to
the running app. If the frontend later needs the real screens end to end, add
C then, as its own decision, with a test proving the route does not exist
outside local.

Risk & rollback: A is one script and one test; deleting them undoes it.
→ Approve A, B, C, or D?
```

## If A is approved, it would be

- `scripts/dev_login.py`: finds the account by phone, mints an access token
  with the same `create_access_token` the login endpoint uses, and prints it
  with the account's role and expiry. It refuses outside `ENVIRONMENT=local`,
  and refuses a phone outside the seed's fake range unless `--any-phone` is
  given, so it is not casually pointed at a real person's account on a
  developer's machine.
- A test that it refuses outside local, and that the token it prints is
  accepted by `GET /api/v1/auth/me`.
- One line in `README.md` and in section 4 of `CLAUDE.md` showing the
  command, which needs both founders' sign-off as a shared-file change.
