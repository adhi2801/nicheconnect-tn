# Testing Standard

**For:** anyone writing code, tests or CI, and anyone about to write "tested" in a report; read in full before the first test (`CLAUDE.md` section 6). **Last checked against the code: 14 October 2026**, on branch `docs/standards-bar`. Every claim below was re-checked then. Five that had stopped being true were corrected; they are listed in section 11.

**The bar** is `CLAUDE.md` section 7.0: **a test is only worth something if it would fail when the code is wrong**, and that is shown, not assumed. "Tested" in any report means the tests below ran in that session and passed. The practice comes from Google's published work on mutation testing and flaky tests, Martin Fowler's on test design and non-determinism, and the documentation of the tools we run (sources in section 12). Each rule says what **enforces** it. A rule nothing enforces is marked *(review only)*.

**The twelve dimensions** (`CLAUDE.md` section 5, D-139), and where this standard serves each:

| Dimension | Here |
|---|---|
| Quality | All of it: what each change needs (1), proof a test can fail (2), the CI gates (9) |
| Security | Every object route's stranger test (1), fuzzing (6), supply-chain gates (9); the rules are `security.md` |
| Privacy and law | Personal data reaches no log, report or embedding, and is in the export (1) |
| Trust and safety | Daily ceilings and blocks on every route that reaches a person (1) |
| Performance | Query-count tests (1), the measurement script and the load test (8) |
| Architecture | The layer contract and the file-kind rules are tests and a CI gate (9) |
| Research | Section 12 |
| Novelty, design, business | Judged by what it catches, against the strongest published test practice (section 0) |
| Reliability | Concurrency tests (4), the overload and failure tests of every outside service (section 0), the migration round trip (9) |
| Maintainability | Tests mirror `app/` (3); every rule shown to fail when broken (2), so a refactor that breaks one is caught |

---

## 0. The benchmarks we beat (Adhi, 6 November 2026: "sky high")

Each row: the strongest published test practice, with its source; ours against it; what enforces it; whether it holds today (measured 6 November 2026). A row marked **(decision)** binds once a founder approves it.

| Benchmark | What the leader publishes | Our bar | Enforced by | Today |
|---|---|---|---|---|
| **Every branch of the core** (SQLite) | 100% branch coverage of the core, and 100% MC/DC; test code 590 times the library's (version 3.42.0, 2023) ([SQLite, "How SQLite is tested", updated 21 April 2026](https://www.sqlite.org/testing.html)) | **100% branch coverage of every rule module** under mutation testing (section 2); 98% of lines overall; every `service.py` at 90% or more | The per-file floors in CI; the rule modules' 100% branch floor as a CI gate (**approved, D-172**) | **Holds**: all ten rule modules at 100% of branches; 98% of lines overall |
| **Proving the tests can fail** (Google) | Mutation testing at Google's scale, surfacing surviving mutants in code review ([ICSE 2018](https://research.google/pubs/state-of-mutation-testing-at-google/)) | Mutation testing nightly on every rule module; no new survivor without a test or a written reason; the floor never raised quietly (section 2) | The nightly run and its floor (D-091, D-139) | **Holds**, its survivors named |
| **Fuzzing as the main effort** (SQLite) | "most testing CPU cycles are now devoted to fuzzing" (same page) | Schemathesis over the whole contract on every push, no input allowed to produce a 500; Hypothesis properties on every pure rule; and a **nightly long run** of both, at ten times the examples (**approved, D-172**) | CI's fuzz step; the nightly job | Per push: **holds**; nightly long run: not yet |
| **Failure on purpose** (SQLite) | Out-of-memory, I/O error, and crash and power-loss tests (same page) | Every outside dependency (the database, Valkey, S3, the Claude API, WhatsApp, the timestamp authorities) has a test of it failing, timing out or refusing, and the answer a person then gets (**approved, D-172**) | A test per dependency, listed in this file | Partly: the database at capacity (load shedding), the Claude API and WhatsApp failures are tested; the list is not yet complete |
| **No flaky test hides a failure** (Google) | Reruns only for tests marked flaky ([Google Testing Blog, 27 May 2016](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)) | No reruns at all: a test that fails once is a failure; a flaky test is fixed, or marked and tracked, the same day | CI runs each test once, stopping at the first failure | **Holds** |

What moves a row from **(decision)** to binding: a founder's yes, recorded in `docs/DECISIONS.md` (`CLAUDE.md` section 5), with its enforcement built in the same change.

---

## 1. What every change needs

| Change | Required tests | Enforced by |
|---|---|---|
| New endpoint | Success; validation failure (422); not logged in (401); another user's object (404, or 403); not found (404); the rate limit applies | Each operation must document 401, 422 and 429 (`tests/test_api_contract.py`); another user's object for every route at once (`tests/modules/test_stranger_routes.py`, item 100) |
| List endpoint | All of the above, plus **pages without gaps or repeats**, and **a query-count test** proving a long page costs the same queries as a short one (`tests/query_counts.py`) | *(review only)*: 18 test files count queries on 17 October |
| State transition | Every allowed transition, and at least one blocked transition (409) | *(review only)*; property tests for the rule-heavy ones |
| A rule checked before a write ("only if", "at most", "not already") | **A concurrency test**: several requests at once, exactly one wins, no raw error reaches a caller (section 4) | *(review only)*: 17 concurrency test files on 24 October |
| Service function | Success and each domain error it can raise | Coverage floor of 90% per `service.py` in CI |
| Model or migration | Each constraint refused by the database itself, by name, written with raw SQL; `upgrade → downgrade → upgrade`; a downgrade that would destroy data refuses while it exists | `tests/test_schema_rules.py` fails on any check or unique constraint no test names; `tests/modules/test_refusing_downgrades.py` runs each refusing downgrade; CI runs the round trip |
| Bug fix | A test that fails before the fix and passes after, seen failing | *(review only)*; said in the commit |
| Personal data | The export includes it (or the exclusion is listed); it reaches no log, error report, trace or embedding | `tests/modules/me/test_export_api.py`; the scrubber, tracer and embedding-input tests |
| Background job | Success, retry on failure, safe when run twice | *(review only)* |
| Public endpoint | Listed in the contract test's public list with its reason; cache headers and 304 if cacheable | `tests/test_api_contract.py` |
| A route that lets one account reach another | Listed in `tests/modules/test_daily_ceilings.py` (a daily ceiling per account), and refused across a block in `tests/modules/safety/test_block_api.py` | Both files check the routes they list exist; a new route missing from them *(review only)* |
| A parser, normaliser or pure rule | **Property tests** (`test_<feature>_properties.py`): what must hold for every input, not just the examples someone thought of (section 6) | *(review only)*; mutation testing finds the gaps for the modules it covers |
| Free text another person reads | Its `text_flags`: what must flag and, just as carefully, ordinary wording that must not | *(review only)* |
| A request body | Refuses unknown fields | `tests/test_architecture.py` |
| A document, or a code comment naming a section | Its decision numbers, paths, links and section references exist | `tests/test_docs.py`, on every run |
| An item built, or a capability audited | `docs/BACKEND_COMPLETE.md` marks it; every built item is named by exactly one capability; section 2's counts are the tables' counts | `tests/test_finish_line.py`, on every run (D-191) |

## 2. Proving a test can fail

For every fix, every concurrency rule, every query-count test and every new guard test, **break the code on purpose, run the test, watch it fail, then restore the code**, and say so in the commit. Examples:
- remove the lock and watch the race test go 1-for-4 the wrong way;
- add a per-row query and watch the count test fail;
- switch off the scrubbing and watch the error-report test see the phone number;
- drop a database rule inside the test's transaction and watch its refusal test fail.

A test never seen failing has not been shown to test anything. **A test that reads a list of things must also prove the list is not empty** (`test_the_request_bodies_are_found`, `test_the_catalogue_is_read`): the first version of the unknown-fields test found no request bodies and passed while checking nothing, until breaking the rule on purpose showed it.

Lessons from 10 October 2026, now rules:
- **At least two of every kind in a query's test.** A filter that forgot to tie a subquery to its row passed every test with one campaign in the database. A test of anything that joins or filters builds two or more of each thing involved (brands, campaigns, creators), so a missing join condition cannot pass by luck.
- **One guard, one test.** Two defences that each cover the other (an email pattern that excluded UPI IDs, and a step that removed emails first) let either be deleted without any test failing. Mutation testing found it. Keep the clearer guard, and give each remaining one a test of its own.

**Mutation testing (mutmut 3.8, D-091)** automates this every night for the rule-heavy files listed in `[tool.mutmut]` (`pyproject.toml`): deal stage, the Merkle proofs, the record's fingerprint, the approval clock, payment state and its dates, the text flags, cursors, the report spreadsheet, and since 8 November a campaign's budget rules, a change's nulls and the ETag comparison (`budget.py`, `partial_update.py`, `http_cache.py`: 81 mutants; the 9 that first survived, an ETag's shape and which field a null names, each now killed by a test), and since 11 November when a Tamil Nadu day ends and whether a campaign takes creators (`clock.py`, `applying.py`; audit C11, D-180).
- It runs in `.github/workflows/mutation.yml` with the machine's clock set to Tamil Nadu time, so code that leans on the machine's zone is caught.
- It fails when more than 21 mutants survive. Each accepted survivor is listed in D-091 as equivalent, or as out of reach with the reason.
- A new survivor gets a test, or a decision; the count is never raised quietly.
- Its first run found real gaps, each now closed by a test: exact boundary days, a reference's length limits, the record's fields and order, and a tampered link in the chain.
- A wider run over more of `app/` left 186 survivors, worked down area by area as item 93.
- Linux only: on Windows, run it in a container, as for CI failures (section 4).

## 3. Layout and naming

```
tests/
  conftest.py              shared fixtures (app client, db session, migration check)
  factories.py             builders for realistic test objects
  deal_flow.py             the deal journey as helpers (campaign → memo → proof → payment)
  query_counts.py          counting the SQL one request runs
  modules/conftest.py      committed rows and held-open writes for concurrency tests
  modules/<module>/
    test_<feature>_api.py      HTTP-level tests
    test_<feature>.py          rules without a database, where the logic is pure
    test_<feature>_properties.py  what holds for every input (Hypothesis)
    test_<feature>_model.py    database constraints
    test_<feature>_concurrency.py
  modules/test_database_refusals.py  database rules broken with raw SQL
  modules/test_refusing_downgrades.py  every downgrade that would destroy data refuses
  modules/test_app_role.py   the app's own login: what it may and may not do
  modules/test_stranger_routes.py  every route that names an object refuses a stranger
  test_api_contract.py     every operation against the committed contract
  test_architecture.py     routers build no queries, services know no HTTP, bodies refuse unknown fields
  owner.py                 the database owner, for the few tests that need more than the app's login
  test_schema_rules.py     the migrated schema read against database.md
  test_check_constraints.py  every CHECK in the models matches the migrated database
  test_banned_terms.py     the money words, across every file and every commit message
  test_docs.py             every document's decision numbers, paths, links and section references exist
  test_finish_line.py      the backend's finish line counts what its tables say
  test_readme_numbers.py   the README's countable numbers are the code's
  test_incident_response.py  every secret the app is given has a rotation step
```

- Test names describe behaviour: `test_a_returning_login_cannot_rewrite_how_it_arrived`, not `test_attribution_2`. *(review only)*
- Arrange → act → assert, with one behaviour per test. *(review only)*
- **Pure rules get pure tests.** A rule written as a function of its inputs (`stage_of`, `decide`, `derive_state`) is tested without a database, every branch, then once end to end through the API.

## 4. Database and concurrency tests

- Run against **real PostgreSQL 18 with pgvector**, never SQLite. The schema is built by the migrations, so tests prove them; pytest stops at once with the fix named if the database is not migrated.
- Each test runs inside a transaction rolled back afterwards. **Tests over aggregate queries use names of their own** (a random city, a unique handle), so rows left by other tests cannot change their counts.
- **Concurrency tests** use real, committed connections (`tests/modules/conftest.py`):
  - several threads start together on a barrier;
  - the moment between check and write is held open (a slow `before_flush` hook, 0.2 to 0.3 s), so the bad ordering happens on every run, not by luck;
  - they assert exactly one success, the rest clean domain errors, and a consistent final state;
  - committed deal-record entries and dispute events are removed through `tests/record_cleanup.py`, which needs a superuser and so uses the owner's connection (`tests/owner.py`); the app's login never has one.
- **CI runs the suite as the app's own login** (item 97, D-100), which may only read and write rows, so code that quietly needs more fails there. Migrations and the release step (`app/db/prepare.py`) run first as the owner; then every test not marked `owner` runs as `nicheconnect_app`; then the `owner` tests run as the owner. Mark a test `owner` only when its own session must be the owner's: a trigger shown refusing, a scratch schema, the triggers set aside for a cleanup. On a laptop both are the same login, unless `OWNER_DATABASE_URL` is set to reproduce CI.
- Factories for data; no hard-coded shared rows.
- **CI is the truth.** A failure that appears only in CI is reproduced, not guessed at: the committed code (`git archive HEAD`) in a Linux container on Python 3.14, against a freshly migrated empty database, with CI's test-only credentials, never a developer's. CI's annotations name each failing test and its first error lines, readable without admin rights.

## 5. External services and time

- WhatsApp, SMS, the Claude API, S3, Sentry and timestamp authorities are never called in tests. Fakes sit behind the same interface, and the test asserts exactly what would have been sent.
- Time comes from an injected clock, never `sleep`, never the machine's clock. Tests move it forward to cross deadlines, midnights and windows, always in Tamil Nadu time where the rule is. The nightly mutation run sets the machine's zone to Tamil Nadu, which catches code that reads it.

## 6. Contract, fuzzing and properties

- The committed OpenAPI contract is compared with the running app on every run (`backend.md` section 2).
- CI fuzzes every operation against the contract (Schemathesis). **Only the "no server error" check gates today**: no generated request, however strange, may produce a 5xx. The other checks wait on `docs/API_CONTRACT_FINDINGS.md`, which is due its own re-check (gap 3). A failure is a bug in the code or the contract, never a reason to loosen either.
- **Property-based tests (Hypothesis 6.169, D-090)** for every parser, normaliser and pure rule. A property test states what holds for **every** input; Hypothesis tries 200 generated cases per test on a laptop, 1,000 on CI (`HYPOTHESIS_PROFILE=ci`) and 50 under mutation testing, and shrinks any failure to its smallest example. Built for cursors, phone numbers, payment references, the record's fingerprint, the Merkle proofs, payment state over time, the approval clock, deal stage, the spreadsheet, and the contact-detail flags.
  - Their first run found a real gap: a mobile number written `987 654 3210` or `09876543210` slipped past the contact-detail flag (item 60). Each shape is now a fixed example too.
  - A property test checks consistency, not a specification: swapping the Merkle hash order kept every proof consistent, and only the RFC 6962 vectors caught it. Keep both kinds.

## 7. Coverage

- **At least 90% for every `service.py` and 80% overall, counting branches**, enforced in CI (D-037). Measured on 14 October: **98.55%** overall, branches counted, over 2,904 tests, every one passing.
- Coverage is a floor, not the goal. A missing failure case fails review even at 100%. Mutation testing (section 2) is the stronger measure, where it runs.

## 8. Performance

- `scripts/measure_performance.py` with seeded data before a phase closes; p95 recorded in `docs/PERFORMANCE.md` against the budgets.
- **The load test** (`scripts/load_test.py`, Locust 2.46, D-092): brands and creators at once, each on a seeded account of their own, failing on any error or any p95 over budget; `--overload` checks that too many people get a quick 503, never a freeze (D-093). Run before a phase closes and before launch; results in `docs/PERFORMANCE.md`. Use `127.0.0.1`, never `localhost`, on Windows. Today's figures are from a laptop; staging from another machine is item 94.

## 9. CI gates (merge is blocked unless all pass)

1. The workflows audited (zizmor)
2. The git history scanned for secrets (Gitleaks)
3. Locked dependencies installed (`uv sync --locked`)
4. Lint and format check (ruff)
5. Type check (mypy strict), then the module layers (`lint-imports`, D-099)
6. New migrations linted for locks (Squawk)
7. Migrations applied, undone and redone on a fresh database; models match the database
8. The full suite: no failures, no unexplained skips. It includes the banned money words in every file and every commit message (`test_banned_terms.py`), files git does not track yet included; the incident plan's rotation steps (`test_incident_response.py`); every document's references (`test_docs.py`); the file-kind rules (`test_architecture.py`); and the schema read against `database.md` (`test_schema_rules.py`)
9. Coverage floors, overall and per `service.py`
10. The API fuzzed against its contract (Schemathesis)
11. Dependency audit (pip-audit): the app's own packages, strictly, and since D-125 every dependency group too (the embeddings image's `ml` group, the load test's, the tools'), so an advisory anywhere we install turns the run red; and every dependency's licence on the approved list (pip-licenses, D-086)
12. Images built and scanned; any fixable vulnerability in the API image blocks (Grype); the API image's bill of materials written (Syft). The embeddings image is built and its scan reported on every push to `main`, for pull requests, and on a branch that changes what goes into it (D-125); until then it was built for pull requests only, and merges made without one (D-101) skipped it
13. Private vulnerability reporting switched on for the repository, since `SECURITY.md` sends researchers there (its own job, `repository-settings`)
14. The OpenTofu files formatted and every environment valid against its locked providers (its own job, `infrastructure`, D-086)
15. The frontend (its own job, `frontend`, D-152): the lockfile installed exactly; the design tokens rebuilt, matching what is committed, with every text and background pair at its contrast floor; the API types regenerated from `docs/api/openapi.json`, matching what is committed, so a contract change reaches the screens as a type error; lint; the web app's unit tests; its production build, which type-checks every page; and the landing page served and read as plain HTML, every heading present without a script (`frontend/scripts/check-no-js.mjs`, D-157). What `docs/standards/frontend.md` section 12 still owes is listed there

Nightly, in its own workflow: **mutation testing** (`mutation.yml`, D-091). A night with more surviving mutants than accepted is a failure to fix the next day, like a red CI.

Every job runs on an exact runner image (`ubuntu-24.04`), never `ubuntu-latest`, so CI cannot change under us (D-086).

**"Blocked" is a convention today, not a lock: `main` has no branch protection** (GitHub's public branch API, 14 October), so nothing stops a merge with a red run (gap 1). CI results are read through GitHub's public API, without a login.

## 10. Honesty

- Never skip, mark as expected-fail, or retry a failing test to get CI green without founder approval and a linked reason. Checked by search on 14 October: no `xfail`, and five skips, each conditional with its reason (three need the `openssl` command; two cover random codes that collide, one in a million).
- A flaky test is a bug: find the cause (usually ordering or shared data) and fix it the same day; never rerun until it passes.
- Never weaken an assertion to make a test pass. Fix the code, or raise the requirement.
- A report names the tests that ran, their count, and anything not run.
- **Grow testing by strength, never by count.** A test is added because it would catch something no other test catches; padding the number is the opposite of the bar.

## 11. Gaps, named

**A claim of mine corrected the same day:** this file said CI had not been seen since early October and nothing had merged to `main` since 1 October. A stale local copy of `main` misled me: Dependabot's updates were merged on 12 October, and CI is now read through GitHub's API. **Closed the same day:** the refusing downgrades untested (item 98).

**Corrected on 14 October:** coverage "about 98%" (measured, section 7); the held-open write "0.1 to 0.4 s" (0.2 to 0.3); the fuzzing "a failure is a bug" without saying only one check gates; the layout missing four files that now enforce rules; and three comments in CI and `pyproject.toml` that sent readers to "testing.md section 5" for coverage, which is section 7.

| # | Gap | Risk | Acting on it |
|---|---|---|---|
| 1 | **`main` has no branch protection**, so a merge with a failing run is not stopped. Until 14 October, a false positive in the secret scan also stopped every run at its second step from 12 October on, unseen, so no later gate ran on GitHub | A red build can reach `main` | A founder turns on branch protection for `main`, requiring the `test`, `image`, `infrastructure`, `frontend` and `repository-settings` jobs |
| 2 | **Two required tests are *(review only)***: the query-count test per list and the concurrency test per "only if" rule. The stranger test per route became mechanical on 14 October (item 100) | One missed test is a missed bug, found by a user | Each gains a check when one is practical |
| 3 | **Fuzzing gates only server errors**, and its findings file was last updated in September, with 64 operations then and 123 routes now | Contract drift the other checks would catch goes unseen | Re-run every check, update the findings, then gate what passes; a CI change, so an Infrastructure gate |
| 4 | **Mutation testing covers eight files**; 186 mutants survived the wider run | Weak tests outside those files are invisible | Item 93 |
| 5 | **The load test ran on a laptop** | Production capacity is an estimate | Item 94 |

## 12. Sources

Each link checked to exist on 14 October 2026.

- [Google: State of Mutation Testing at Google (ICSE 2018)](https://research.google/pubs/state-of-mutation-testing-at-google/), and [mutmut](https://mutmut.readthedocs.io/).
- [Google Testing Blog: Flaky Tests at Google and How We Mitigate Them](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html); [Martin Fowler: Eradicating Non-Determinism in Tests](https://martinfowler.com/articles/nonDeterminism.html).
- [Martin Fowler: The Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html).
- [Hypothesis](https://hypothesis.readthedocs.io/en/latest/): property-based testing and shrinking.
- [Schemathesis](https://schemathesis.readthedocs.io/): fuzzing from the OpenAPI contract.
- [Locust](https://docs.locust.io/): the load test.
- [coverage.py](https://coverage.readthedocs.io/): branch coverage.
- [RFC 6962](https://www.rfc-editor.org/rfc/rfc6962): the Merkle tree test vectors.

## 13. How this file is kept true

- Re-checked against the code and the workflows whenever it is read for work, and at least monthly with `docs/PLATFORM_AND_TECH_PLAN.md`'s review.
- A rule that gains enforcement says so; a rule found untrue is corrected in the same change (`docs/README.md` section 0).
