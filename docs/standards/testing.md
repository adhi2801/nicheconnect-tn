# Testing Standard

Applies to all code. "Tested" in any report means the tests below ran in that session and passed.

---

## 1. What every change needs

| Change | Required tests |
|---|---|
| New endpoint | Success; validation failure (422); not logged in (401); another user's object (403/404); not found (404); rate limit applies |
| State transition | Every allowed transition, and at least one blocked transition (409) |
| Service function | Success and each domain error it can raise |
| Model or migration | Constraints enforced (unique, check, FK); `upgrade → downgrade → upgrade` works |
| Bug fix | A test that fails before the fix and passes after |
| Embedding input | Proof that PII fields are excluded |
| Background job | Success, retry on failure, safe when run twice |

## 2. Layout and naming

```
tests/
  conftest.py              shared fixtures (app client, db session, auth helpers)
  factories.py             builders for realistic test objects
  modules/<module>/
    test_<feature>_api.py      HTTP-level tests
    test_<feature>_service.py  business-rule tests
  migrations/
    test_migrations.py
```

- Test names describe behaviour: `test_brand_cannot_view_other_brands_campaign`, not `test_campaign_2`.
- Arrange → act → assert, with one behaviour per test.

## 3. Database tests

- Run against **real PostgreSQL with pgvector** (Docker locally, a service container in CI). No SQLite substitutes.
- Each test runs inside a transaction that is rolled back afterwards, so tests never depend on each other or on order.
- Migrations, not `create_all`, build the test schema, so tests prove migrations work.
- Use factories for data; no hard-coded shared rows.

## 4. External services

- WhatsApp, SMS, Claude API and email are never called in tests. Use fakes behind the same interface, and assert what would have been sent.
- Time-dependent logic (OTP expiry, token expiry) uses an injectable clock, never `sleep`.

## 5. Coverage

- **≥ 90%** for every `service.py` file and **≥ 80%** overall, counting branches as well as lines. CI enforces both (D-037).
- Coverage is a floor, not the goal. Missing failure-case tests fail review even when coverage is high.

## 6. Performance checks

- Seed data script plus a simple timing test for list and matching endpoints before a phase closes. Record p95 in the PR against the budgets in `backend.md`.
- A query-count assertion on list endpoints guards against N+1 regressions.

## 7. CI gates (merge is blocked unless all pass)

1. Install pinned dependencies
2. Lint and format check (D-037)
3. Type check (D-037)
4. `alembic upgrade head` on a fresh database, then downgrade and upgrade again
5. `pytest` with no failures and no skipped tests without a reason
6. Dependency vulnerability audit (D-031)
7. Banned-term check from CLAUDE.md section 2

## 8. Honesty

- Never mark a test as skipped or expected-fail to get CI green without founder approval and a linked reason.
- Never weaken an assertion to make a test pass. Fix the code or discuss the requirement.
