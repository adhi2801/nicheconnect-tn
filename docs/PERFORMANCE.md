# Performance, measured

Numbers from `scripts/measure_performance.py`, not estimates. The quality bar
in `CLAUDE.md` section 7 says performance figures come from tools; this file
is where they live.

**Budgets** (`docs/standards/backend.md` section 6): p95 ≤ 300 ms for reads,
≤ 500 ms for writes, on seeded local data.

**Last measured:** 23 September 2026, on PostgreSQL 18.6 with pgvector 0.8.6
(D-049), seeded with 10 brands, 200 creators, 150 campaigns, 786
applications. 100 runs per endpoint, on a developer laptop under Docker
Desktop for Windows.

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `GET /campaigns/discover` | 9.6 | 18.1 | 300 | OK |
| `GET /campaigns/discover?city&niche` | 10.5 | 15.7 | 300 | OK |
| `GET /campaigns` (mine) | 11.7 | 14.7 | 300 | OK |
| `GET /campaigns/{id}` | 9.9 | 14.8 | 300 | OK |
| `GET /campaigns/{id}/applications` | 13.5 | 18.0 | 300 | OK |
| `GET /applications/me` | 11.9 | 14.0 | 300 | OK |
| `GET /auth/me` | 9.3 | 15.6 | 300 | OK |
| `PATCH /brands/me` | 12.5 | 15.9 | **500** | OK |
| `PATCH /creators/me` | 12.7 | 18.0 | **500** | OK |
| `POST /campaigns` | 15.3 | 17.1 | **500** | OK |

Every endpoint is inside budget with roughly twenty to thirty times the
headroom. **Writes are measured as of 23 September**, having never been
checked before: they run the whole write path — auth, validation, the
idempotency route class, the UPDATE or INSERT, and the commit — and come in
at about a thirtieth of their 500 ms budget.

The two PATCHes rewrite the same row each run and add nothing. `POST
/campaigns` writes one row per run, and the script removes them again and
reports how many; the row count was verified back at 150 afterwards.

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
venv\Scripts\python.exe scripts\measure_performance.py --runs 100
```

Add `--explain` to see the query plans behind each endpoint and confirm the
indexes are used.
