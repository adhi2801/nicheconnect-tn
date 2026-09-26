# Performance, measured

Numbers from `scripts/measure_performance.py`, not estimates. The quality bar
in `CLAUDE.md` section 7 says performance figures come from tools; this file
is where they live.

**Budgets** (`docs/standards/backend.md` section 6): p95 ≤ 300 ms for reads,
≤ 500 ms for writes, on seeded local data.

**Last measured:** 26 September 2026, on PostgreSQL 18.6 with pgvector 0.8.6
(D-049), seeded with 10 brands, 200 creators, 150 campaigns, 785
applications and 958 rate card packages. 100 runs per read. For writes: 30
whole deals, 5 bank bulk transfers of 25 rows, and 30 rounds of rate card
edits. All from one run, on a developer laptop under Docker Desktop for
Windows.

## Reads

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `GET /campaigns/discover` | 9.1 | 11.8 | 300 | OK |
| `GET /campaigns/discover?city&niche` | 9.9 | 16.2 | 300 | OK |
| `GET /campaigns` (mine) | 12.5 | 19.9 | 300 | OK |
| `GET /campaigns/{id}` | 9.5 | 12.9 | 300 | OK |
| `GET /campaigns/{id}/applications` | 13.3 | 15.4 | 300 | OK |
| `GET /applications/me` | 15.0 | 25.0 | 300 | OK |
| `GET /auth/me` | 8.7 | 11.9 | 300 | OK |
| `GET /creators/{id}/media-kit` (10 packages) | 12.9 | 15.8 | 300 | OK |
| `GET /creators/by-handle/{handle}` (10 packages) | 9.9 | 12.9 | 300 | OK |
| `GET /rate-guidance` (niche and city) | 12.5 | 21.8 | 300 | OK |

## Writes

Every write a deal can go through, **including the deal record entry each one
seals** (D-057), plus the bank bulk transfer and the rate card. They run
inside one transaction that is rolled back, so the measurement leaves nothing
behind; that matters because a deal record entry cannot be deleted once
written.

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `POST /campaigns` | 12.3 | 17.7 | 500 | OK |
| `POST /campaigns/{id}/publish` | 13.7 | 18.5 | 500 | OK |
| `POST /campaigns/{id}/applications` | 14.6 | 19.4 | 500 | OK |
| `POST /applications/{id}/shortlist` | 16.4 | 21.4 | 500 | OK |
| `POST /applications/{id}/accept` | 16.3 | 20.4 | 500 | OK |
| `POST /deal-memos/for-application/{id}` | 16.2 | 22.8 | 500 | OK |
| `POST /deal-memos/{id}/send` | 20.5 | 24.3 | 500 | OK |
| `POST /deal-memos/{id}/accept` | 20.4 | 25.4 | 500 | OK |
| `POST /deal-memos/{id}/proof` | 23.3 | 27.9 | 500 | OK |
| `POST /deal-memos/{id}/proof/{id}/approve` | 26.8 | 29.9 | 500 | OK |
| `POST /deal-memos/{id}/payment/mark-paid` | 23.3 | 25.6 | 500 | OK |
| `POST /deal-memos/{id}/payment/dispute` | 18.5 | 21.4 | 500 | OK |
| `POST .../payment/dispute/entries` | 17.6 | 23.2 | 500 | OK |
| `POST .../payment/dispute/close` | 18.5 | 25.1 | 500 | OK |
| `POST /deal-memos/{id}/payment/confirm` | 23.2 | 30.3 | 500 | OK |
| `POST /brands/me/payments/mark-paid` (25 rows) | 289.0 | 313.7 | 500 | OK, see below |
| `PUT /creators/me/channels/{platform}` | 11.9 | 16.5 | 500 | OK |
| `POST /creators/me/packages` | 13.1 | 18.0 | 500 | OK |
| `PATCH /creators/me/packages/{id}` | 13.1 | 16.7 | 500 | OK |
| `DELETE /creators/me/packages/{id}` | 10.8 | 14.3 | 500 | OK |
| `POST /creators/me/rate-card/publish` | 12.2 | 15.6 | 500 | OK |
| `POST /creators/me/rate-card/unpublish` | 11.6 | 14.4 | 500 | OK |

**The bulk mark-paid is the one to watch.** At its limit of 25 rows it uses
about two-thirds of the write budget: roughly 12 ms a row, because each row
takes its own lock, writes its own notification and seals its own deal record
entry, exactly as a single mark-paid does (D-043 chose that on purpose). It
is inside the budget with room, but it is the write most sensitive to a
slower database. **If the 25-row limit is ever raised, measure again first.**
Only 5 bulk calls were timed in this run, so its p95 is close to its maximum;
the other writes had 30 samples each.

The deal steps cost about 5 to 10 ms more than the campaign steps. That is
the record: a row lock on the deal, the parties' account ids, the previous
seal, and one insert. It buys a history nobody can quietly rewrite.

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

## The deal record's daily proof, and when it will need work

A proof (`GET /deal-memos/{id}/record/proof`) rebuilds that day's tree from
every deal on the platform, then walks it, so its cost grows with the number
of deals, not with the one asked about. The tree itself, measured on
27 September:

| Deals on the platform | Root | One proof's path |
| --- | --- | --- |
| 1,000 | 1.6 ms | 1.6 ms |
| 10,000 | 17.1 ms | 18.2 ms |
| 50,000 | 95.5 ms | 92.5 ms |

A proof does both, plus one query that reads a row per deal. At pilot scale
that is a few milliseconds. **Somewhere between 30,000 and 50,000 deals it
approaches the 300 ms read budget.** The fix is to store each checkpoint's
tree levels once, when the checkpoint is written, so a proof reads about 16
hashes instead of rebuilding the tree. That is a schema change, so it waits
for its own decision. **Trigger:** 20,000 deals, or a measured proof p95 above
150 ms, whichever comes first.

## What is not measured yet

- **Writes beyond the deal, disputes, bulk mark-paid and the rate card.**
  Profile and campaign edits are single-row writes of the same kind, but they
  are not in the script yet.
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
