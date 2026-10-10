# Scaling later: proposals, each with the measured trigger that would justify it

`CLAUDE.md` section 3 sends every future-scale idea here instead of into the code: **we build for pilot scale, and change the architecture only when a measured number says to.** Each row below is a proposal, not a decision. Acting on one needs both founders, a decision entry, and the measurement that crossed its trigger, from a tool (`docs/PERFORMANCE.md`), never from a feeling.

Written 10 October 2026, from the triggers earlier decisions already named. Before this file existed those triggers were scattered through `docs/DECISIONS.md`; they are gathered here, unchanged.

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

## What never comes here without both founders

From `CLAUDE.md` section 3:
- Kafka or another message broker;
- Kubernetes;
- more than one region;
- a service mesh;
- GraphQL;
- a dedicated vector or search database.

Data stays in Mumbai (`docs/standards/legal.md` sections 3.1 and 3.2), which makes more than one region a legal question as well as a technical one.

## How a proposal is added

One row: what, the trigger as a number a tool can measure, what we do until then, and where it came from. A proposal whose trigger cannot be measured is not ready for this file.
