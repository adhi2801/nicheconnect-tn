# Database Standard

Applies to models, migrations, queries and pgvector. Every schema change also needs founder approval (CLAUDE.md section 5).
Rules marked **(decision)** need a recorded decision before first use.

---

## 1. Naming

- Tables: singular `snake_case` (`brand`, `campaign`, `deal_memo`). Keep consistent with existing tables.
- Columns: `snake_case`. Foreign keys: `<table>_id`. Booleans: `is_…` / `has_…`. Timestamps: `…_at`. Dates: `…_on`.
- Constraint names are set explicitly through a SQLAlchemy naming convention on `Base.metadata`:
  `pk_%(table_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `ix_%(table_name)s_%(column_0_name)s`.
  Without this, migrations can't reliably drop constraints later.

## 2. Column types

| Data | Type | Never |
|---|---|---|
| Primary key | `UUID` with `gen_random_uuid()` default | serial integers exposed in the API |
| Timestamps | `TIMESTAMPTZ`, stored in UTC, `server_default=now()` | `TIMESTAMP` without time zone |
| Money | `BIGINT` paise **or** `NUMERIC(12,2)` **(decision, one for the whole schema)** | `FLOAT`, `REAL`, `DOUBLE` |
| Short text | `VARCHAR(n)` with a real limit | unbounded `String` for user input |
| Long text | `TEXT` with an app-level length limit | |
| Status / type fields | `VARCHAR` + `CHECK` constraint listing the allowed values | free text |
| Tags (niches, languages, cities) | `TEXT[]` with a GIN index, or a lookup table when values need metadata **(decision)** | comma-separated strings |
| Email | `VARCHAR(320)`, stored lowercase; uniqueness on `lower(email)` | case-sensitive uniqueness |
| Phone | `VARCHAR(16)` in E.164 | local formats |
| Embeddings | `vector(<dim>)`, with the dimension fixed by decision | |

- Every table has `id`, `created_at`, `updated_at`. `updated_at` is maintained by the app (`onupdate`) or a trigger. Pick one approach for the whole schema.
- `NOT NULL` is the default. A nullable column needs a reason.

## 3. Integrity

- Every relationship has a real `FOREIGN KEY` with an explicit `ON DELETE` (`CASCADE`, `RESTRICT` or `SET NULL`) chosen per relationship and documented in the migration.
- Business rules the database can enforce, it must: `UNIQUE (campaign_id, creator_id)`, `CHECK (budget_min <= budget_max)`, `CHECK (amount > 0)`.
- One row per real-world thing: one deal memo per application, one payment status per deal memo (unique FK).
- Deletion policy (hard delete, soft delete with `deleted_at`, or anonymise) follows the DPDP answer from the validation pack. **(decision)** Until then, don't add `deleted_at` columns speculatively.

## 4. PII and embeddings

- Tables with a `vector` column never contain raw PII columns (phone, email, bank, UPI, government IDs, legal names). Contact details live in separate tables keyed by ID (e.g. `creator_contact`).
- Embedding input is built by one function that only reads allow-listed, non-PII fields. That function has a test proving PII fields are excluded.
- Bank and UPI identifiers are not stored at all unless a founder decision says otherwise.

## 5. Indexes

- Every foreign key column is indexed.
- Every column used in a `WHERE`, `ORDER BY` or `JOIN` on a list endpoint has a supporting index, usually composite in filter-then-sort order (`(brand_id, created_at DESC)`).
- Partial indexes for hot subsets: `WHERE status = 'open'`.
- GIN indexes for array or JSONB containment queries.
- pgvector: HNSW index with `vector_cosine_ops` once a table has real embeddings; build parameters **(decision)** after measuring recall on sample data.
- No index without a query that uses it. Check with `EXPLAIN (ANALYZE, BUFFERS)` and include the plan in the PR for new hot queries.

## 6. Migrations

- Generated with `alembic revision --autogenerate`, then **read and edited by hand**. Autogenerate misses things: server defaults, check constraints, extensions, enum changes, renames it treats as drop plus add.
- One logical change per migration, with a descriptive message: `add campaign table`, not `update`.
- Every migration has a working `downgrade()`. CI runs `upgrade head → downgrade base → upgrade head` on a fresh database.
- Extensions (`vector`, `pgcrypto`) are created in migrations with `IF NOT EXISTS`.
- **Zero-downtime pattern (expand → migrate → contract)** for changes to tables that hold real data:
  1. Add the new column or table as nullable, or with a default.
  2. Deploy code that writes to both; backfill in batches.
  3. Switch reads; then drop the old column in a later migration.
- Never rename or drop a column in the same deploy as the code that stops using it.
- Data migrations (backfills) are separate from schema migrations, batched (≤ 1,000 rows per transaction) and re-runnable.
- Never edit a migration that has been merged to `main`. Write a new one.

## 7. Queries

- Use the SQLAlchemy 2.0 `select()` style. Raw SQL only with bound parameters, never string formatting.
- List queries always have a `LIMIT`.
- Never `SELECT *` in raw SQL; select the columns you need.
- Transactions stay short: no network calls inside them.
- Connection pool settings live in config: pool size, overflow, `pool_pre_ping=True`, statement timeout (e.g. 5 s) set per connection.

## 8. Test data

- A seed script creates realistic Tamil Nadu sample data (brands, creators across cities and niches, campaigns in each status) for local development and performance checks.
- Seed data uses obviously fake contact details (`+9100000000xx`, `@example.com`).
- Never copy production data to a local machine.
