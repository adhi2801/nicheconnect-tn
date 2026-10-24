# Scaling later: proposals, each with the measured trigger that would justify it

`CLAUDE.md` section 3 sends every future-scale idea here instead of into the code: **we build for pilot scale, and change the architecture only when a measured number says to.** Each row below is a proposal, not a decision. Acting on one needs both founders, a decision entry, and the measurement that crossed its trigger, from a tool (`docs/PERFORMANCE.md`), never from a feeling.

**For:** anyone proposing to change how the system scales, read before the proposal (`CLAUDE.md` section 7.0). Written 10 October 2026, from the triggers earlier decisions already named; **last checked against the code and infra on 14 October 2026**, when S8 and S9 were added from measured capacity (D-093) and the connection arithmetic below.

## The order we scale in

Cheapest and most reversible first:
1. **Measure.**
2. **Fix the query**: an index, a rewritten query, one query instead of many.
3. **A bigger instance.**
4. **More instances of the same service.**
5. **Only then a new kind of component.**

Steps 1 to 4 need no architecture change. Step 5 is what this file is for.

## The proposals

| # | Proposal | Trigger that would justify it | Until then | From |
|---|---|---|---|---|
| S1 | **Asynchronous database access** in the API | Measured request concurrency, where waiting on the database (not the CPU) holds the p95 over budget, after steps 2 to 4 | Synchronous SQLAlchemy throughout (`backend.md` section 6) | D-009 |
| S2 | **An HNSW vector index** on the embedding tables | Matching's measured read p95 over the 300 ms budget in `docs/PERFORMANCE.md` | Exact search inside a structurally filtered set, which is always exactly right at pilot scale | D-052 |
| S3 | **Background jobs in their own service**, not inside the API (`RUN_JOBS`) | Job runs measurably raising the API's p95, or needing a different size of machine | Jobs run inside the API service; several instances may share the work | D-060 |
| S4 | **A Postgres read replica** for heavy reads (search, city figures, exports) | Database CPU sustained above 70% at peak, or read p95 over budget after step 2 | One primary, Multi-AZ in production (`infra/`) | New, 10 October |
| S5 | **Text search beyond `ILIKE`**: first a `pg_trgm` index in Postgres; a dedicated search engine only after that | Creator search p95 over budget. `pg_trgm` is an index (step 2); a search engine is a new service and needs both founders (`CLAUDE.md` section 3) | `ILIKE` over a filtered set | New, 10 October |
| S6 | **Partitioning the largest append-only tables** (notifications, the deal record) by month | A table's size making its own queries miss budget after indexing, or its vacuum running too long | Plain tables with the indexes each list needs | New, 10 October |
| S7 | **A CDN in front of public pages** (the Passport, city figures) | Public read traffic large enough that cache misses raise API load measurably | `Cache-Control` and `ETag` on those answers already (`backend.md` section 2) | New, 10 October |
| S8 | **Autoscaling the API on requests per container** (item 88). More instances is step 4, but it changes the infrastructure, so it is recorded here | One container held 400 people at once with no errors, and shed load with a quick 503 at 800 (D-092, D-093, measured on a laptop). Trigger: shed 503s above 0.1% of requests at peak, or in-flight requests per container sustained near `MAX_IN_FLIGHT_REQUESTS` | A fixed count: 2 containers in production, 1 in staging (`infra/envs/`) | D-093, 14 October |
| S9 | **A connection pooler in front of Postgres** (RDS Proxy, or PgBouncer in transaction mode) | Each API container may open up to 15 connections for the app (`DB_POOL_SIZE` 5 + `DB_MAX_OVERFLOW` 10) and up to 20 for DBOS's own pool (its default), so 35. A db.t4g.small allows about 200 (AWS: memory ÷ 9,531,392 bytes). Trigger: containers × 35, plus the release step, above 80% of `max_connections`: about 4 containers today, so before S8 lets the count grow past 3 | First the cheap step 2: give DBOS a pool sized to its work (`sys_db_pool_size`), which roughly halves the per-container count. PgBouncer in transaction mode needs psycopg's prepared statements switched off; RDS Proxy does not, but costs per vCPU | New, 14 October |
| S10 | **Keep each brand's look-alike flag** instead of working it out on read (item 75) | Every page of campaigns reads every brand with a verified domain, and the admin list reads every brand (D-118). Trigger: `GET /campaigns/discover` p95 over budget, or more than about 2,000 verified brands | Worked out on each read: one query per page however long, measured with the page's other reads | D-118, 24 October |
