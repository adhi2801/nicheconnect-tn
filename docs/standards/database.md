# Database Standard

Applies to tables, migrations, indexes, queries and pgvector. Read before any of them. The bar is `CLAUDE.md` section 7.0. The database is the last line of defence: **a rule the database can enforce, it must**, so a bug in the code, a script or a hand-written query still cannot break it.

Rules marked **(decision)** need a recorded founder decision before first use.

---

## 1. Naming

- Tables: singular `snake_case` (`brand`, `campaign`, `deal_memo`).
- Columns: `snake_case`. Foreign keys: `<table>_id`. Booleans: `is_…` / `has_…`. Timestamps: `…_at`. Dates: `…_on`.
- Constraint names are set explicitly through the naming convention on `Base.metadata`: `pk_%(table_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `ix_%(table_name)s_%(column_0_name)s`. A check's name says the rule in words (`ck_account_attribution_code_means_invite`), because it is what an error message names.

## 2. Column types

| Data | Type | Never |
|---|---|---|
| Primary key | `UUID`; **`uuidv7()` for every new table** (time-ordered, so inserts stay fast and ids sort by creation; PostgreSQL 18, D-047). Older tables keep `gen_random_uuid()`. | serial integers exposed in the API |
| Timestamps | `TIMESTAMPTZ`, stored in UTC, `server_default=now()` | `TIMESTAMP` without time zone |
| Time of day | `TIME`, meaning Tamil Nadu time, documented on the column | a string |
| Money | `BIGINT` whole paise (D-015), with a `currency` column checked to `'INR'` | `FLOAT`, `REAL`, `NUMERIC` for amounts |
| Short text | `VARCHAR(n)` with a real limit | unbounded `String` for user input |
| Long text | `TEXT` with a length `CHECK` or an app-level limit | |
| Status / type fields | `VARCHAR` + `CHECK` listing the allowed values, mirrored by a `Literal` tied to it in tests | free text, Postgres `ENUM` (painful to change) |
| Tags (niches, languages, cities) | `TEXT[]` with a GIN index and a containment `CHECK` against the allowed list | comma-separated strings |
| Email | `VARCHAR(320)`, stored lowercase; unique on `lower(email)` | case-sensitive uniqueness |
| Phone | `VARCHAR(16)` in E.164 | local formats |
| Embeddings | `vector(<dim>)`, dimension fixed by decision (D-052) | |

- Every table has `id`, `created_at`, `updated_at`. The app sets `updated_at` on every change, in the same statement.
- `NOT NULL` is the default. A nullable column says why in a comment ("NULL means never published").

## 3. Integrity

- Every relationship has a real `FOREIGN KEY` with an explicit `ON DELETE` chosen per relationship and **explained in the migration's docstring**:
  - `CASCADE` for a person's own things;
  - `RESTRICT` for records of money and deals, which must never vanish as a side effect;
  - `SET NULL` where history must outlive a link.
- **Every business rule the database can hold, it holds.**
  - Uniqueness, such as one memo per application or one payment record per memo.
  - Ranges and allowed values.
  - "Both or neither" pairs (`(quiet_from IS NULL) = (quiet_until IS NULL)`).
  - Implications (`confirmed_at IS NULL OR marked_paid_at IS NOT NULL`).
  - Each has a test that writes the forbidden row with raw SQL and watches the database refuse it.
- Append-only tables (the deal record, dispute events, the admin log) are never updated or deleted by the app; their seals prove it (D-057).
- Deletion policy (hard delete, anonymise, retain) follows the validation pack's DPDP answer **(decision)**. Until then no `deleted_at` columns.

## 4. PII and embeddings

- Tables with a `vector` column never contain raw PII (phone, email, bank, UPI, government IDs, legal names) (constraint 2).
- Embedding input is built by one function that reads only allow-listed, non-PII fields, and a test proves PII is excluded.
- Bank and UPI identifiers are not stored unless a founder decision says otherwise.
- Every column holding personal data is in the person's data export, or listed in `export_service.NOT_EXPORTED` with the reason; a test fails if a table is neither.

## 5. Indexes

- Every foreign key column is indexed (a unique constraint counts).
- Every column used in a `WHERE`, `ORDER BY` or `JOIN` on a list endpoint has a supporting index, composite in filter-then-sort order (`(brand_id, created_at DESC)`).
- Partial indexes for hot subsets (`WHERE marked_paid_at IS NULL`). GIN for array or JSONB containment.
- pgvector: HNSW with `vector_cosine_ops` once a table has real embeddings; build parameters **(decision)** after measuring recall.
- No index without a query that uses it. New hot queries show their `EXPLAIN (ANALYZE, BUFFERS)` plan in the pull request.

## 6. Migrations

- Generated with `uv run alembic revision --autogenerate`, then **read and edited by hand**. The docstring says what changes, why, each `ON DELETE` choice, the data impact, and what the downgrade does.
- One logical change per migration, with a descriptive message: `add notification_preference (D-079)`.
- **One new migration in flight at a time** (`CLAUDE.md` section 1): commit one before generating the next, so the chain cannot fork.
- Every migration has a working `downgrade()`. CI runs `upgrade head → downgrade base → upgrade head` on a fresh database and checks the models match the database.
- **A downgrade that would destroy data that can never be recovered refuses** while that data exists (the deal record's kinds, attribution), with a message saying why. Losing it must be a deliberate act, not a rollback.
- **No migration may block writes on a table that holds data** (Squawk lints every new migration in CI, D-050):
  - a new constraint on an existing table is added `NOT VALID`, then validated in a separate step outside the transaction;
  - indexes on existing tables are built `CONCURRENTLY`;
  - a change to an allowed-values list is staged (new check beside the old, swap, validate).
  
  New, empty tables may have their constraints and indexes created whole.
- **Expand → migrate → contract** for changes to tables with real data: add the new column nullable or defaulted; deploy code that writes both and backfill in batches; switch reads; drop the old one in a later migration. Never rename or drop a column in the same deploy as the code that stops using it.
- Backfills are separate from schema migrations, batched (≤ 1,000 rows per transaction) and re-runnable.
- Never edit a migration merged to `main`. Write a new one.

## 7. Queries

- SQLAlchemy 2.0 `select()` style. Raw SQL only with bound parameters, never string formatting.
- List queries always have a `LIMIT`; pages are keyset (`(created_at, id) < cursor`), never `OFFSET`.
- A request makes a fixed number of queries whatever its page size (`backend.md` section 6).
- Never `SELECT *` in raw SQL.
- Transactions stay short: no network calls inside them. A row that a rule depends on is locked before the rule is checked (`backend.md` section 5).
- Every connection has a statement timeout (5 s by default, `DB_STATEMENT_TIMEOUT_MS`); the pool uses `pool_pre_ping`.

## 8. Operations

- **Backups:** automated, with point-in-time recovery: 14 days in production, 1 in staging (`infra/`). Deletion protection on in production.
- **A restore is tested before launch**, and once a quarter after, by restoring into a scratch instance and running the app's readiness check against it. A backup never restored is not a backup.
- **Recovery targets (decision before launch):** proposed at most 5 minutes of data lost and 1 hour to restore.
- **Watching it:** Performance Insights is on in production. `pg_stat_statements` reports the slowest queries weekly against the budgets **(not yet used)**.
- The app's database user owns nothing it does not need: no superuser, no `CREATE` outside migrations (`security.md` section 9).

## 9. Test data

- `scripts/seed_dev_data.py` creates realistic Tamil Nadu sample data (brands, creators across cities and niches, campaigns in each status) for local development and performance checks.
- Seed data uses obviously fake contact details (`+9100000000xx`, `@example.com`).
- Never copy production data to a local machine.
