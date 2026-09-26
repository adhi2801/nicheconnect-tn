# Performance, measured

Numbers from `scripts/measure_performance.py`, not estimates. The quality bar
in `CLAUDE.md` section 7 says performance figures come from tools; this file
is where they live.

**Budgets** (`docs/standards/backend.md` section 6): p95 ≤ 300 ms for reads,
≤ 500 ms for writes, on seeded local data.

**Last measured:** 26 September 2026, on PostgreSQL 18.6 with pgvector 0.8.6
(D-049), seeded with 10 brands, 200 creators, 150 campaigns, 785
applications and 958 rate card packages. 100 runs per read; for writes, 30
whole deals taken from a new campaign to a confirmed payment. On a developer
laptop under Docker Desktop for Windows.

## Reads

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `GET /campaigns/discover` | 8.8 | 11.6 | 300 | OK |
| `GET /campaigns/discover?city&niche` | 8.5 | 11.5 | 300 | OK |
| `GET /campaigns` (mine) | 10.2 | 12.7 | 300 | OK |
| `GET /campaigns/{id}` | 8.1 | 10.9 | 300 | OK |
| `GET /campaigns/{id}/applications` | 11.6 | 14.6 | 300 | OK |
| `GET /applications/me` | 10.1 | 13.0 | 300 | OK |
| `GET /auth/me` | 7.0 | 8.4 | 300 | OK |
| `GET /creators/{id}/media-kit` (10 packages) | 11.7 | 14.5 | 300 | OK |
| `GET /creators/by-handle/{handle}` (10 packages) | 8.6 | 10.7 | 300 | OK |
| `GET /rate-guidance` (niche and city) | 10.5 | 15.1 | 300 | OK |

## Writes

Every write in a deal's life, **including the deal record entry each one
seals** (D-057). They run inside one transaction that is rolled back, so the
measurement leaves nothing behind; that matters because a deal record entry
cannot be deleted once written.

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `POST /campaigns` | 10.6 | 12.2 | 500 | OK |
| `POST /campaigns/{id}/publish` | 12.0 | 13.5 | 500 | OK |
| `POST /campaigns/{id}/applications` | 13.0 | 14.9 | 500 | OK |
| `POST /applications/{id}/shortlist` | 14.0 | 15.0 | 500 | OK |
| `POST /applications/{id}/accept` | 14.3 | 17.7 | 500 | OK |
| `POST /deal-memos/for-application/{id}` | 13.9 | 18.3 | 500 | OK |
| `POST /deal-memos/{id}/send` | 18.8 | 30.5 | 500 | OK |
| `POST /deal-memos/{id}/accept` | 18.6 | 25.8 | 500 | OK |
| `POST /deal-memos/{id}/proof` | 20.8 | 25.9 | 500 | OK |
| `POST /deal-memos/{id}/proof/{id}/approve` | 24.5 | 32.2 | 500 | OK |
| `POST /deal-memos/{id}/payment/mark-paid` | 21.4 | 26.4 | 500 | OK |
| `POST /deal-memos/{id}/payment/confirm` | 21.3 | 57.2 | 500 | OK |

The deal steps cost about 5 to 10 ms more than the campaign steps. That is
the record: a row lock on the deal, the parties' account ids, the previous
seal, and one insert. It is well inside the budget and it buys a history
nobody can quietly rewrite.

**Not yet in the script:** dispute writes, the bulk mark-paid, and rate card
writes. Each is a single-row write of the kind measured above, so there is no
reason to expect a surprise, but "no reason to expect" is not a measurement.

## PostgreSQL 18 did not make us faster, and that is fine

`docs/PLATFORM_AND_TECH_PLAN.md` gives PostgreSQL 18's asynchronous I/O as
worth "up to 2 to 3 times faster reads". **Our own measurement does not show
that**, and D-047's upgrade rule is explicit that a benchmark on someone
else's application does not count.

Measured the same day, same seed, same machine, 100 runs each:

| Endpoint | 16.15 p95 ms | 18.6 p95 ms |
| --- | --- | --- |
| `GET /campaigns/discover` | 12.7 | 12.4 |
| `GET /campaigns/discover?city&niche` | 11.1 | 10.9 |
| `GET /campaigns` (mine) | 11.7 | 15.8 |
| `GET /campaigns/{id}` | 10.5 | 9.6 |
| `GET /campaigns/{id}/applications` | 17.6 | 15.4 |
| `GET /applications/me` | 12.5 | 12.3 |
| `GET /auth/me` | 8.0 | 9.3 |

The two are indistinguishable. The differences are smaller than the
run-to-run variation: a first run against a freshly started 18 container read
several milliseconds slower across the board, and matched 16 once the cache
was warm.

**Why there is nothing to see.** Asynchronous I/O helps a workload that waits
on disk. At 150 campaigns and 786 applications the whole dataset sits in
memory, so there is no disk wait to remove. The gain, if it comes, comes at a
data size we do not have yet.

**This does not argue against 18.** The reasons in D-049 stand and none of
them was speed: native `uuidv7()`, statistics that survive an upgrade, exact
image tags, and pgvector pinned clear of CVE-2026-3172. The plan's row has
been corrected so nobody quotes a speed win we have not seen.

## What is not measured yet

- **Some writes.** The deal's whole path is measured; disputes, bulk
  mark-paid and rate card writes are not yet.
- **Under load.** These are sequential requests from one client. The plan
  (section 4.5) wants a repeatable load test before launch; it does not exist.
- **At real scale.** 150 campaigns is a pilot-sized seed, not a year of
  trading. The figures say the queries are not accidentally quadratic; they
  do not say what happens at a hundred times the rows.
- **Anywhere but a laptop.** No hosting is chosen, so there is no staging
  number. A managed database across a network will not look like this.

## Running it yourself

```powershell
docker compose up -d
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe scripts\seed_dev_data.py
venv\Scripts\python.exe scripts\measure_performance.py --runs 100 --deals 30
```

Add `--explain` to see the query plans behind each endpoint and confirm the
indexes are used.
