# Testing Standard

Applies to all code. "Tested" in any report means the tests below ran in that session and passed. The bar is `CLAUDE.md` section 7.0: **a test is only worth something if it would fail when the code is wrong**, and that is shown, not assumed.

---

## 1. What every change needs

| Change | Required tests |
|---|---|
| New endpoint | Success; validation failure (422); not logged in (401); another user's object (403/404); not found (404); the rate limit applies |
| List endpoint | All of the above, plus **pages without gaps or repeats**, and **a query-count test** proving a long page costs the same queries as a short one |
| State transition | Every allowed transition, and at least one blocked transition (409) |
| A rule checked before a write ("only if", "at most", "not already") | **A concurrency test**: several requests at once, exactly one wins, no raw error reaches a caller (section 4) |
| Service function | Success and each domain error it can raise |
| Model or migration | Each constraint refused by the database itself, written with raw SQL; `upgrade → downgrade → upgrade` |
| Bug fix | A test that fails before the fix and passes after |
| Personal data | The export includes it (or the exclusion is listed); it reaches no log, error report or embedding |
| Background job | Success, retry on failure, safe when run twice |
| Public endpoint | Listed in the contract test's public list with its reason; cache headers and 304 if cacheable |

## 2. Proving a test can fail

For every fix, every concurrency rule and every query-count test, **break the code on purpose, run the test, watch it fail, then restore the code**, and say so in the commit. Examples:
- remove the lock and watch the race test go 1-for-4 the wrong way;
- add a per-row query and watch the count test fail;
- switch off the scrubbing and watch the error-report test see the phone number.

A test never seen failing has not been shown to test anything.

Mutation testing tools (mutmut) automate this for the rule-heavy modules (payment state, deal stage, approval clock) **(not yet used; a dependency decision)**.

## 3. Layout and naming

```
tests/
  conftest.py              shared fixtures (app client, db session, migration check)
  factories.py             builders for realistic test objects
  deal_flow.py             the deal journey as helpers (campaign → memo → proof → payment)
  modules/conftest.py      committed rows and held-open writes for concurrency tests
  modules/<module>/
    test_<feature>_api.py      HTTP-level tests
    test_<feature>.py          rules without a database, where the logic is pure
    test_<feature>_model.py    database constraints
    test_<feature>_concurrency.py
  test_api_contract.py     every operation against the committed contract
  test_banned_terms.py     the money words, across every tracked file
```

- Test names describe behaviour: `test_a_returning_login_cannot_rewrite_how_it_arrived`, not `test_attribution_2`.
- Arrange → act → assert, with one behaviour per test.
- **Pure rules get pure tests.** A rule written as a function of its inputs (`stage_of`, `decide`, `derive_state`) is tested without a database, every branch, then once end to end through the API.

## 4. Database and concurrency tests

- Run against **real PostgreSQL 18 with pgvector**, never SQLite. The schema is built by the migrations, so tests prove them; pytest stops at once with the fix named if the database is not migrated.
- Each test runs inside a transaction rolled back afterwards. **Tests over aggregate queries use names of their own** (a random city, a unique handle), so rows left by other tests cannot change their counts.
- **Concurrency tests** use real, committed connections (`tests/modules/conftest.py`):
  - several threads start together on a barrier;
  - the moment between check and write is held open (a slow `before_flush` hook, 0.1 to 0.4 s), so the bad ordering happens on every run, not by luck;
  - they assert exactly one success, the rest clean domain errors, and a consistent final state.
- Factories for data; no hard-coded shared rows.

## 5. External services and time

- WhatsApp, SMS, the Claude API, S3, Sentry and timestamp authorities are never called in tests. Fakes sit behind the same interface, and the test asserts exactly what would have been sent.
- Time comes from an injected clock, never `sleep`, never the machine's clock. Tests move it forward to cross deadlines, midnights and windows, always in Tamil Nadu time where the rule is.

## 6. Contract, fuzzing and supply chain

- The committed OpenAPI contract is compared with the running app on every run (`backend.md` section 2).
- CI fuzzes every operation against the contract (Schemathesis); a failure is a bug in the code or the contract, never a reason to loosen either (`docs/API_CONTRACT_FINDINGS.md`).
- Property-based tests (Hypothesis) for parsers and normalisers (phone numbers, codes, cursors) **(not yet used; a dependency decision)**.

## 7. Coverage

- **≥ 90%** for every `service.py` and **≥ 80%** overall, counting branches, enforced in CI (D-037). Today the whole suite is at about 98%.
- Coverage is a floor, not the goal. A missing failure case fails review even at 100%.

## 8. Performance

- `scripts/measure_performance.py` with seeded data before a phase closes; p95 recorded in `docs/PERFORMANCE.md` against the budgets.
- A repeatable load test with many users is owed before launch (item 5 in `docs/BACKEND_COMPLETE.md`).

## 9. CI gates (merge is blocked unless all pass)

1. The workflows audited (zizmor)
2. The git history scanned for secrets (Gitleaks)
3. Locked dependencies installed (`uv sync --locked`)
4. Lint and format check (ruff)
5. Type check (mypy strict)
6. New migrations linted for locks (Squawk)
7. Migrations applied, undone and redone on a fresh database; models match the database
8. The full suite: no failures, no unexplained skips. It includes the banned money words in every file and every commit message (`test_banned_terms.py`). Files git does not track yet are scanned too, so a laptop sees what CI will. It also checks that the incident plan can rotate every secret the app is given (`test_incident_response.py`)
9. Coverage floors, overall and per `service.py`
10. The API fuzzed against its contract (Schemathesis)
11. Dependency audit (pip-audit)
12. Images built and scanned; any fixable vulnerability blocks (Grype); the API image's bill of materials written (Syft)
13. Private vulnerability reporting switched on for the repository, since `SECURITY.md` sends researchers there (its own job, `repository-settings`)

## 10. Honesty

- Never skip, mark as expected-fail, or retry a failing test to get CI green without founder approval and a linked reason.
- A flaky test is a bug: find the cause (usually ordering or shared data) and fix it the same day; never rerun until it passes.
- Never weaken an assertion to make a test pass. Fix the code, or raise the requirement.
- A report names the tests that ran, their count, and anything not run.
