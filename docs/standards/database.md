# Database Standard

**For:** anyone adding or changing a table, migration, index, query or pgvector use, read in full before the first file (`CLAUDE.md` section 6). **Last checked against the code: 14 October 2026**, on branch `docs/standards-bar`, by reading the migrated database's own catalogue, not the models. Every claim below was re-checked then. Ten that had stopped being true were corrected; they are listed in section 10.

**The bar** is `CLAUDE.md` section 7.0. The database is the last line of defence: **a rule the database can enforce, it must**, so a bug in the code, a script or a hand-written query still cannot break it. The practice comes from PostgreSQL's own documentation, the PostgreSQL wiki's "Don't Do This", GitLab's and Stripe's published migration practice, and Squawk (sources in section 12). Each rule says what **enforces** it. A rule nothing enforces is marked *(review only)*.

Rules marked **(decision)** need a founder decision in `docs/DECISIONS.md` before first use. Rules marked **(not yet used)** apply the first time the situation arises.

**The ten dimensions** (`CLAUDE.md` section 5), and where this standard serves each:

| Dimension | Here |
|---|---|
| Quality | Every rule names its enforcement; the schema is read by tests, section 3 |
| Architecture | One database, tables owned by modules (`backend.md` section 1); pgvector in the same database, section 5 |
| Security | Bound parameters only (7); the app's own database login, rows only, section 8 |
| Privacy and law | No personal data in embeddings, every personal column exported or explained, section 4; every table erased, emptied, held or not personal on deletion (D-122), section 3 |
| Trust and safety | Append-only, sealed records nobody can quietly rewrite, section 3 |
| Performance | Indexes (5), keyset pages and fixed query counts (7), statement timeouts |
| Research | Section 12 |
| Novelty, design, business | Not here: a database standard is judged by integrity, not by competitors. What the screens need is `backend.md` |

---

## 1. Naming

- Tables: singular `snake_case` (`brand`, `campaign`, `deal_memo`). Columns: `snake_case`; foreign keys `<table>_id`. *(review only)*
- Timestamps end `_at` and are `TIMESTAMPTZ`. **Enforced by** `tests/test_schema_rules.py`. One named exception: `deal_record_checkpoint.covers_until`, a moment that reads as a phrase.
- Dates end `_on` where it reads naturally, or are a phrase that says the date (`booked_until`, `figures_as_of`, `post_date`). *(review only)*
- Booleans read as a true-or-false statement: `is_…`, `has_…`, or a predicate such as `auto_approved`, `handle_matches`, `disclosure_required`. The schema's six booleans are all predicates. *(review only)*
- Constraint names come from the naming convention on `Base.metadata` (`app/db/base.py`): `pk_%(table_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `ix_%(table_name)s_%(column_0_name)s`. A check's name says the rule in words (`ck_account_attribution_code_means_invite`), because it is what an error message names and what a test matches.

## 2. Column types

| Data | Type | Never | Enforced by |
|---|---|---|---|
| Primary key | `UUID`; **`uuidv7()`** (RFC 9562's time-ordered UUID, so inserts stay in index order and ids sort by creation; PostgreSQL 18, D-047). The 15 tables made before 26 September keep `gen_random_uuid()`; two tables keyed by their owner's id (the embeddings) have no id of their own | serial integers exposed in the API | `tests/test_schema_rules.py`: a new table without `uuidv7()` fails |
| Timestamps | `TIMESTAMPTZ`, stored in UTC, `server_default=now()` | `TIMESTAMP` without time zone | `tests/test_schema_rules.py` |
| Time of day | `TIME`, meaning Tamil Nadu time, said on the column (quiet hours, D-079) | a string | *(review only)* |
| Money | `BIGINT` whole paise (D-015), on a table with a `currency` column checked to `'INR'`. One exception: an application's quote answers a campaign and is in its currency | `FLOAT`, `REAL`, `NUMERIC`, `MONEY` | `tests/test_schema_rules.py` |
| Short text | `VARCHAR(n)` with a real limit | unbounded `VARCHAR` | `tests/test_schema_rules.py` |
| Long text | `TEXT` with a length `CHECK` | `TEXT` with no limit | `tests/test_schema_rules.py` |
| Allowed values | `VARCHAR` + `CHECK` listing them, built from the same tuple as the API's `Literal`; `app/core/literals.py` stops the app starting if the two drift | free text; Postgres `ENUM` (an allowed value cannot be removed from one) | `tests/test_schema_rules.py` (no enums); `ensure_same_values` at import |
| Tags | `TEXT[]` with a cardinality `CHECK`. From a fixed vocabulary (niches, languages, muted types): a containment `CHECK` against it. Free text (cities): each element is limited by the API | comma-separated strings | the `CHECK`s; `tests/test_check_constraints.py` |
| Email | `VARCHAR(320)`, stored lowercase by a `CHECK` (`email = lower(email)`), so a plain unique constraint is case-insensitive | case-sensitive uniqueness | the `CHECK` |
| Phone | `VARCHAR(16)` in E.164 | local formats | `CHECK`s on `account` and `otp_challenge` |
| Embeddings | `vector(<dim>)`, the dimension fixed by D-052 | | `tests/modules/matching/test_embedding_model.py` |

- Every table has `id`, `created_at` and `updated_at`, except the named ones: the two embedding tables are keyed by their owner; the four append-only tables have no `updated_at`, because they are never updated; `deal_record_entry`'s moment is `recorded_at`, inside its seal (D-057). **Enforced by** `tests/test_schema_rules.py`. The app sets `updated_at` in the same statement as every change. *(review only)*
- `NOT NULL` is the default. A nullable column says what NULL means, in a comment beside it in the model ("NULL means never published"). *(review only)*: the schema has 90 nullable columns.

## 3. Integrity

- Every relationship has a real `FOREIGN KEY` with an `ON DELETE` chosen for it: `CASCADE` for a person's own things; `RESTRICT` for records of money and deals, which must never vanish as a side effect; `SET NULL` where history must outlive a link. Today: 17, 17 and 1. **Enforced by** `tests/test_schema_rules.py`, which fails on PostgreSQL's unchosen default (`NO ACTION`). Why each was chosen goes in the migration's docstring. *(review only)*
- **Every business rule the database can hold, it holds**: uniqueness (one memo per application), ranges and allowed values, "both or neither" pairs (`(quiet_from IS NULL) = (quiet_until IS NULL)`), and implications (`confirmed_at IS NULL OR marked_paid_at IS NOT NULL`). 159 checks and 25 unique constraints on 14 October.
- **Each one has a test that writes the forbidden row with raw SQL and watches the database refuse it, by name** (`pytest.raises(IntegrityError, match="<rule>")`). **Enforced by** `tests/test_schema_rules.py`, which fails if any rule is never named by a test. It is a name check, so it proves each rule is named, not that its test is right. On 14 October it found 21 rules no test named; `tests/modules/test_database_refusals.py` now breaks each. One rule cannot be broken alone and is named there with the reason.
- **The models and the migrations hold the same checks.** `alembic check` compares columns, indexes and keys but not checks; `tests/test_check_constraints.py` compares those.
- **Append-only tables refuse every change at the database**: `UPDATE`, `DELETE` and `TRUNCATE` are refused by trigger on the deal record (its entries, checkpoints and outside timestamps) the admin log (D-057), dispute events (item 99), deal notes (item 17, D-128) and deal feedback (item 77, D-136). **Enforced by** `tests/test_schema_rules.py` and each table's model tests. **And by permission**: the app's own login may only read and insert on these seven tables (section 8), so a change is refused before a trigger is reached, and the login cannot switch the triggers off (`tests/modules/test_app_role.py`). Only the owner, used by the release step alone, could.
- **Deleting an account** (item 6, D-122) deletes its own rows, empties the `account`, `brand` and `creator` rows deals point at, and keeps what a law may require under a retention setting left unset until the validation pack gives the period. `account.deleted_at` is the one `deleted_at` column: the row stays as "someone who left", its phone NULL, which only a deleted account may be (`ck_account_phone_until_deleted`). Every table is placed exactly once in `app/modules/me/account_deletion_registry.py`. **Enforced by** `tests/modules/me/test_account_deletion_registry.py`, and `test_account_deletion_erasure.py`, which fills every erased table and counts each empty for the person and untouched for a bystander.

## 4. Personal data and embeddings

- Tables with a `vector` column never contain raw personal data: phone, email, bank, UPI, government IDs, legal names (constraint 2). The two embedding tables hold an owner's id and the vector only.
- Embedding input is built by one function from allow-listed fields. **Enforced by** `tests/modules/matching/test_embedding_input_model.py`: every creator and campaign column is declared embedded or deliberately not, a field that looks private cannot be declared, and no private value reaches the text.
- Bank and UPI identifiers are not stored unless a founder decision says otherwise. UPI IDs: D-085, in `creator_upi` only, with consent, never a phone number.
- Every table is in the person's data export or listed in `export_service.NOT_EXPORTED` with the reason. **Enforced by** `tests/modules/me/test_export_api.py`.

## 5. Indexes

- **Every foreign key is indexed** by an index whose first column is the key (a unique constraint counts). Without one, deleting the parent row scans the whole child table (PostgreSQL documentation, section 12). A partial index counts only when it leaves out nothing but NULLs: one limited to open rows cannot find a closed one. **Enforced by** `tests/test_schema_rules.py`, with no exceptions since item 98 indexed the four that lacked one on 14 October.
- Every column used in a `WHERE`, `ORDER BY` or `JOIN` on a list has a supporting index, composite in filter-then-sort order (`(account_id, created_at)`). *(review only)*; the query counts in `tests/query_counts.py` catch the per-row queries, not a missing index.
- Partial indexes for hot subsets (`WHERE status = 'open'`, `WHERE read_at IS NULL`). GIN for array or JSONB containment **when a query uses it**: `creator.niches` has one; campaigns' niches and cities do not, because measured at 20,000 campaigns the planner chose the open-campaign index and filtered (D-017).
- **No index without a query that uses it.** A new hot query shows its `EXPLAIN (ANALYZE, BUFFERS)` plan in the pull request. *(review only)*
- pgvector: no vector index yet. Exact search is right at pilot scale. HNSW with `vector_cosine_ops` comes when a table has enough real embeddings to need it, with its build parameters **(decision)** chosen after measuring recall.

## 6. Migrations

- Generated with `uv run alembic revision --autogenerate`, then **read and edited by hand**. The docstring says what changes, why, each `ON DELETE` choice, the data impact, and what the downgrade does. One logical change per migration, named for it: `add notification_preference (D-079)`. *(review only)*
- **One new migration in flight at a time** (`CLAUDE.md` section 1), so the chain cannot fork. **Enforced by** `tests/test_migration_check.py` (exactly one head) and a check that the test database is current before any test runs.
- Every migration has a working `downgrade()`. **Enforced by** CI: `upgrade head`, `downgrade base`, `upgrade head` on a fresh database, then `alembic check` for drift.
- **A downgrade that would destroy data that can never be recovered refuses** while that data exists (the admin log, invitations, answered dates, attribution, proof files and their readings, UPI IDs, blocks, the deal record's kinds, reports for impersonation or intimate content, takedowns, admins' authenticators, brands' verified domains, new UPI IDs waiting their 24 hours, new phone numbers waiting their 72 hours, or their 7 days without the current number, data exports being prepared or with a file still stored, passkeys, notices that one of a person's sessions was ended, admins' clearances of look-alike brand names, accounts waiting to be deleted or deleted, counter-offers on quotes, numbers holding both a brand and a creator account, memos sealed with their deliverables, deal notes, brands' saved creator lists, creators' campaign alerts, barter shipments and their sealed entries, connected accounts and the deletions Meta asked for, feedback on finished deals, assistants' tokens, drafts and memos sealed with terms version 3), with a message saying why. Losing it must be a deliberate act, not a rollback. Thirty-two migrations do this. **Enforced by** `tests/modules/test_refusing_downgrades.py`, which writes the guarded data and runs each real `downgrade()` on the test's rolled-back connection; it also fails if a migration starts or stops refusing without its list changing (item 98).
- **No migration may block writes on a table that holds data.** **Enforced by** Squawk 2.65.0 in CI on every migration a branch adds (D-050; `.squawk.toml` says which rules are off and why):
  - a new constraint on an existing table is added `NOT VALID`, then validated in a separate step (D-089 is the latest example);
  - indexes on existing tables are built `CONCURRENTLY`;
  - a change to an allowed-values list is staged: the new check beside the old, swap, validate.

  New, empty tables may have their constraints and indexes created whole.
- **Expand, migrate, contract** for changes to tables with real data: add the new column nullable or defaulted; deploy code that writes both and backfill; switch reads; drop the old one in a later migration. Never rename or drop a column in the same deploy as the code that stops using it (Stripe and GitLab, section 12). **(not yet used)**: no table has real data yet.
- Backfills are separate from schema migrations, batched (at most 1,000 rows per transaction) and re-runnable. **(not yet used)**
- Never edit a migration merged to `main`. Write a new one. *(review only)*

## 7. Queries

- SQLAlchemy 2.0 `select()` style. Raw SQL only with bound parameters, never string formatting (OWASP). **Enforced by** ruff's S608 rule in CI, in `app/` and in tests.
- Lists are bounded: keyset pages (`(created_at, id) < cursor`), never `OFFSET` (none in `app/`), or a whole list only where a rule caps it (`backend.md` section 2).
- A request makes a fixed number of queries whatever its page size. **Enforced by** a query-count test on every list (`tests/query_counts.py`; `backend.md` section 6).
- Never `SELECT *` in raw SQL. *(review only)*
- Transactions stay short: no network calls inside them. A row a rule depends on is locked before the rule is checked (`backend.md` section 5). *(review only)* for the first; concurrency tests prove the locks.
- Every connection has a statement timeout (5 s by default, `DB_STATEMENT_TIMEOUT_MS`), the pool uses `pool_pre_ping`, and a request waits at most `DB_POOL_TIMEOUT_SECONDS` for a connection before a 503 (D-093). Set in `app/db/session.py`.

## 8. Operations

- **Backups:** automated, with point-in-time restore to any second in the window: 14 days in production, 1 in staging; deletion protection and a final snapshot in production; storage encrypted; not publicly reachable (`infra/modules/app/data.tf`). Described, not yet deployed.
- **A restore is tested before launch** (D-062), and monthly after (item 90), by restoring into a scratch instance and running the app's readiness check against it. A backup never restored is not a backup. **Not yet done**: nothing is deployed.
- **Recovery targets (decision before launch):** proposed at most 5 minutes of data lost and 1 hour to restore.
- **Watching it:** Performance Insights and PostgreSQL logs to CloudWatch are on in production. A weekly slow-query report from `pg_stat_statements` against the budgets is item 95 **(not yet built)**.
- **The app's database login owns nothing and can only read and write rows** (item 97, D-100):
  - `app_writer`, a role without a login, holds the rights: `SELECT`, `INSERT`, `UPDATE` and `DELETE` on every table; only `SELECT` and `INSERT` on the six sealed tables; no `DELETE` on `takedown`, whose rows the IT Rules keep (item 52); only `SELECT` on `alembic_version`; no `TRUNCATE`, no ownership, nothing that creates objects. Migration `0dbcaacb1030` grants them, and later tables get the row rights by default; a later sealed table revokes the rest itself.
  - `nicheconnect_app`, the login the API and the nightly task use, is a member. The release step (`app/db/prepare.py`, the migration task) is the one thing that connects as the owner: it runs the migrations, makes DBOS's schema with `app_writer`'s access, and sets the login's password, sent as a SCRAM verifier so no log can hold it (`app/db/roles.py`).
  - **Enforced by** `tests/modules/test_app_role.py`, which reads every table's rights from the catalogue, shows the login refused at each way around the rules, and runs a whole deal, a dispute and a report through the API on it; and by CI, which runs the suite as that login and only the tests marked `owner` as the owner (`testing.md` section 4).

## 9. Test data

- `scripts/seed_dev_data.py` creates realistic Tamil Nadu sample data (brands, creators across cities and niches, campaigns in each status) for local development and performance checks.
- Seed data uses obviously fake contact details: phones from `+9190000` (a range that still passes the database's Indian-mobile rule) and emails `@example.com`.
- Never copy production data to a local machine. Tests and load tests run against their own throwaway data and roll it back.

## 10. Gaps, named

**Corrected on 14 October**, each found by reading the catalogue: the app's database user (it owned every table: fixed by item 97); every foreign key indexed (four were not: fixed by item 98); dispute events sealed (they were not: fixed by item 99); every table having `id`, `created_at` and `updated_at` (six named exceptions); booleans named `is_…` (none are); dates named `_on` (three are not); a GIN index and a vocabulary check on every tag list (one index, and cities are free text); allowed values tied "in tests" (stronger: at import); restores "quarterly" (monthly, as item 90 says); and the sample phones (`+9100000000xx` cannot be stored).

**Closed the same day** (D-100): the app connecting as the table owner (item 97), four foreign keys without a usable index (item 98), dispute events unsealed (item 99), and the refusing downgrades untested (item 98).

| # | Gap | Risk | Acting on it |
|---|---|---|---|
| 1 | **No restore has ever been tested, and recovery targets are not decided** | A backup that fails when needed | D-062 point 5 before the first user; item 90 monthly after |
| 2 | **No slow-query report** | Slow queries found by users, not by us | Item 95 |
| 3 | **Free-text cities are limited per element only by the API** | A script writing directly could store a very long city | A per-element length check when the campaign table next changes |
| 4 | Several rules are *(review only)*, among them nullable columns explaining NULL and `EXPLAIN` plans in pull requests | They hold only while someone reads for them | Each gains a test when one is practical; eleven gained one on 14 October, and the app's login, the indexes and the refusing downgrades the next change |

## 11. How this file is kept true

- Re-checked against the migrated database whenever it is read for work, and at least monthly with `docs/PLATFORM_AND_TECH_PLAN.md`'s review.
- A rule with known exceptions names them in its test, and the test fails both when a new table breaks the rule and when an exception is fixed without the list changing, so neither this file nor the test can drift from the schema.
- A rule found untrue is corrected in the same change (`docs/README.md` section 0).

## 12. Sources

Each link checked to exist on 14 October 2026.

- PostgreSQL 18 documentation: [UUID functions, `uuidv7()`](https://www.postgresql.org/docs/18/functions-uuid.html); [constraints](https://www.postgresql.org/docs/18/ddl-constraints.html), including why a referencing column should usually be indexed; [`ALTER TABLE`](https://www.postgresql.org/docs/18/sql-altertable.html): `NOT VALID`, `VALIDATE CONSTRAINT`, and that the owner may disable triggers; [`CREATE INDEX … CONCURRENTLY`](https://www.postgresql.org/docs/18/sql-createindex.html); [`GRANT`](https://www.postgresql.org/docs/18/sql-grant.html).
- [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562): UUID version 7.
- [PostgreSQL wiki: Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This): `timestamp` without time zone, `money`, and the rest.
- [Squawk](https://squawkhq.com/): the migration linter (D-047, D-050).
- [GitLab migration style guide](https://docs.gitlab.com/development/migration_style_guide/) and [batched background migrations](https://docs.gitlab.com/development/database/batched_background_migrations/).
- [Stripe: online migrations at scale](https://stripe.com/blog/online-migrations): the dual-write pattern behind expand, migrate, contract.
- [Use The Index, Luke: no offset](https://use-the-index-luke.com/no-offset): keyset pagination.
- [OWASP SQL injection prevention cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): bound parameters, least privilege for the database account.
- [pgvector](https://github.com/pgvector/pgvector): exact search, HNSW and its build parameters.
- AWS RDS: [the master user's privileges](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.MasterAccounts.html) and [point-in-time restore](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html).
