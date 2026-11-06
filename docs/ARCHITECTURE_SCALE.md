# Scaling later: proposals, each with the measured trigger that would justify it

`CLAUDE.md` section 3 sends every future-scale idea here instead of into the code: **we build for pilot scale, and change the architecture only when a measured number says to.** Each row below is a proposal, not a decision. Acting on one needs both founders, a decision entry, and the measurement that crossed its trigger, from a tool (`docs/PERFORMANCE.md`), never from a feeling.

**For:** anyone proposing to change how the system scales, read before the proposal (`CLAUDE.md` section 7.0). Written 10 October 2026; **last checked against the code and `infra/` on 6 November 2026**, with the research of that day (`docs/research/BACKEND_RESEARCH_2026.md`): S2, S5 and S9 corrected, the connection arithmetic redone against the database's cores, and the cheaper steps the research found listed before any proposal.

---

## 0. The benchmarks we beat

| Benchmark | What the leader publishes | Our bar | Enforced by | Today |
|---|---|---|---|---|
| **Scale by measurement, cheapest step first** (AWS) | The Well-Architected Framework's performance-efficiency pillar: select resources by data, review as workloads change, experiment more often | No architecture change without a measured trigger crossed (this file); the five-step order below | Both founders' approval and a decision entry (`CLAUDE.md` section 5) | **Holds**: no proposal acted on early |
| **Know the capacity before the traffic** (Google SRE) | Capacity planning from load tests, with headroom for the loss of one instance (*Site Reliability Engineering*, "Software Engineering in SRE" and "Handling Overload") | One container's ceiling measured (400 people, D-093) and overload shed with a quick 503 | `scripts/` load test (item 5); shedding (item 5a) | Measured on a laptop only; from another machine is item 94 |
| **Connections sized to the database, not the app** (PostgreSQL project) | Active connections near (database cores × 2) + effective spindles, the spindles zero when the working set is cached; more makes throughput fall (HikariCP wiki, "About Pool Sizing", formula from the PostgreSQL project) | Requests admitted per container capped (`MAX_IN_FLIGHT_REQUESTS` 12) below its pool; the total checked against the database (item 112) | `Settings` refuses an in-flight cap at or above the pool (`app/core/config.py`) | **Partly**: the per-container rule holds; the total across containers is not checked (S9) |

## The order we scale in

Cheapest and most reversible first:
1. **Measure.**
2. **Fix the query**: an index, a rewritten query, one query instead of many.
3. **A bigger instance.**
4. **More instances of the same service.**
5. **Only then a new kind of component.**

Steps 1 to 4 need no architecture change. Step 5 is what this file is for.

**Steps 1 to 3 already known, to take before any proposal below** (from the research of 6 November, each an item in `docs/BACKEND_COMPLETE.md`):
- PostgreSQL 18's asynchronous reads: measure `io_method` `worker` against `io_uring` on the production image (item 109).
- PostgreSQL 18's skip scan: read every composite index against its queries; one may now serve where two did (item 110).
- Size DBOS's own pool (`sys_db_pool_size`) to its work: not yet done, and it is most of each container's connection count (S9).
- A startup check that the configured connections, at the autoscaler's maximum, fit the database (item 112).

## The proposals

| # | Proposal | Trigger that would justify it | Until then | From |
|---|---|---|---|---|
| S1 | **Asynchronous database access** in the API | Measured request concurrency, where waiting on the database (not the CPU) holds the p95 over budget, after steps 2 to 4 | Synchronous SQLAlchemy throughout (`backend.md` section 6) | D-009 |
| S2 | **An HNSW vector index** on the embedding tables, with pgvector's iterative scans switched on (`hnsw.iterative_scan`), or a city-and-niche filter silently returns short lists (pgvector 0.8; item 111) | Matching's measured read p95 over the 300 ms budget in `docs/PERFORMANCE.md` | Exact search inside a structurally filtered set, always exactly right at pilot scale; no vector index exists (checked 6 November) | D-052 |
| S3 | **Background jobs in their own service**, not inside the API (`RUN_JOBS`) | Job runs measurably raising the API's p95, or needing a different size of machine | Jobs run inside the API service; several instances may share the work | D-060 |
| S4 | **A Postgres read replica** for heavy reads (search, city figures, exports) | Database CPU sustained above 70% at peak, or read p95 over budget after step 2 | One primary, Multi-AZ in production (`infra/`) | 10 October |
| S5 | **Text search beyond what Postgres holds**: first a `pg_trgm` index for creator search's names and handles; a dedicated search engine only after that | Creator search p95 over budget. `pg_trgm` is an index (step 2); a search engine is a new service and needs both founders (`CLAUDE.md` section 3) | Creator search matches names, handles and bios with `ILIKE` over a filtered set (`search_service.py`); matching's word ranking reads words stored per row (D-173), so it is not part of this trigger | 10 October; corrected 6 November |
| S6 | **Partitioning the largest append-only tables** (notifications, the deal record) by month | A table's size making its own queries miss budget after indexing, or its vacuum running too long | Plain tables with the indexes each list needs | 10 October |
| S7 | **A CDN in front of public pages** (the Passport, city figures) | Public read traffic large enough that cache misses raise API load measurably | `Cache-Control` and `ETag` on those answers already (`backend.md` section 2); the website's own cached public pages (frontend item F343) | 10 October |
| S8 | **Autoscaling the API on requests per container** (item 88). More instances is step 4, but it changes the infrastructure, so it is recorded here | One container held 400 people at once with no errors, and shed load with a quick 503 at 800 (D-092, D-093, measured on a laptop). Trigger: shed 503s above 0.1% of requests at peak, or in-flight requests per container sustained near `MAX_IN_FLIGHT_REQUESTS` | A fixed count: 2 containers in production, 1 in staging (`infra/envs/`) | D-093 |
| S9 | **A connection pooler in front of Postgres** (PgBouncer 1.25 in transaction mode, or RDS Proxy; item 113) | Two limits, the tighter first. **Throughput:** production's `db.t4g.small` has 2 vCPUs, so the PostgreSQL project's formula puts efficient active connections near 4 to 5; each container admits up to 12 requests at once, so two containers can already ask for 24 at a time, and a third makes the database, not the app, the queue. **Count:** each container may open 15 app connections (`DB_POOL_SIZE` 5 + `DB_MAX_OVERFLOW` 10) and up to 20 for DBOS (its default), 35 in all, against about 200 allowed (AWS: memory ÷ 9,531,392 bytes). Trigger: the load test (item 94) showing database waits holding p95 over budget, or containers × 35 above 80% of `max_connections` | Step 2 first: size DBOS's pool to its work, and lower the in-flight cap if the load test shows database waits. PgBouncer 1.25 keeps psycopg's prepared statements working with `max_prepared_statements` above zero (its documentation; a February 2026 report shows the failure when left at zero); RDS Proxy pins a connection on session state and costs per vCPU | 14 October; corrected 6 November |
| S10 | **Keep each brand's look-alike flag** instead of working it out on read (item 75) | Every page of campaigns reads every brand with a verified domain, and the admin list reads every brand (D-118). Trigger: `GET /campaigns/discover` p95 over budget, or more than about 2,000 verified brands | Worked out on each read: one query per page however long, measured with the page's other reads | D-118 |

## The twelve dimensions, for this file

| Dimension | Here |
|---|---|
| Quality | Each trigger is a number a tool reports; each proposal's "until then" is what is built and tested today |
| Novelty | None claimed: scaling well is matching the best published practice, not inventing |
| Architecture | The modular monolith holds until a row here is acted on (`CLAUDE.md` section 3) |
| Research | Section 0 and the sources below, read 6 November 2026 |
| Security | A pooler (S9) and a CDN (S7) each sit in the request path: each needs its own security review when proposed |
| Privacy and law | A CDN must never cache a personal answer: only public, consented pages (S7) |
| Trust and safety | None |
| Performance | The whole file |
| Design | None: no proposal changes what a screen receives |
| Business | Every step costs money (bigger instance, replica, pooler); the order keeps cost behind need |
| Reliability | S4 and S8 change how the system fails; each needs its failure test (`testing.md`) when acted on |
| Maintainability | Each proposal is reversible to its "until then" column |

## Gaps, named

1. **Every capacity number was measured on a laptop**, never from another machine against staging (item 94). Triggers S8 and S9 rest on them.
2. **The connection total across containers is not checked by anything** (item 112), and DBOS's pool is unsized.
3. **No production metrics exist yet**: nothing is deployed, so no trigger can be crossed by real traffic; the first month's numbers re-check every row.

## Sources (read 6 November 2026)

- AWS Well-Architected Framework, performance efficiency pillar: https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html
- Google, *Site Reliability Engineering*, "Handling Overload": https://sre.google/sre-book/handling-overload/
- HikariCP, "About Pool Sizing" (the PostgreSQL project's formula): https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing
- AWS RDS, maximum connections by instance memory: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Limits.html
- pgvector 0.8 iterative index scans: https://pgxn.org/dist/vector/0.8.0/README.html
- PgBouncer 1.25 documentation: https://pigsty.io/docs/pgbouncer/ ; pgsql-general, February 2026: https://postgrespro.com/list/id/CAJCZkoJr=Az5PMDj15O5ekzK+vK454WzoWZdQ9XUfTkTWtCQGw@mail.gmail.com
- PostgreSQL 18 release notes: https://www.postgresql.org/docs/18/release-18.html
