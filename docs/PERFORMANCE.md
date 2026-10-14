# Performance, measured

Numbers from `scripts/measure_performance.py`, not estimates. The quality bar
in `CLAUDE.md` section 7 says performance figures come from tools; this file
is where they live.

**Budgets** (`docs/standards/backend.md` section 6): p95 ≤ 300 ms for reads,
≤ 500 ms for writes, on seeded local data.

**Last measured:** 30 September 2026 for creator search and reports (next
section); 26 September 2026 for everything else, on PostgreSQL 18.6 with pgvector 0.8.6
(D-049), seeded with 10 brands, 200 creators, 150 campaigns, 785
applications and 958 rate card packages. 100 runs per read. For writes: 30
whole deals, 5 bank bulk transfers of 25 rows, and 30 rounds of rate card
edits. All from one run, on a developer laptop under Docker Desktop for
Windows.

## Added 14 October: two new reads, and the bulk write at its edge

Measured with `scripts/measure_performance.py` on 600 campaigns, 3,986 applications, 900 creators and 4,641 packages, on a laptop.

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `GET /reports/mine` (item 102), 50 runs | 16.3 | 20.2 | 300 | OK |
| `GET /deal-memos/{id}/calendar.ics` (item 69), 30 deals | 13.4 | 19.7 | 300 | OK |

The calendar file is timed inside the script's write deals, because only those have agreed dates; the seeded data has no accepted deal.

**The bulk mark-paid (25 rows) is at the edge of its 500 ms budget in this harness, and today's figures do not settle which side.** Six runs gave a p95 of 615.8, 555.7, 543.5, 443.7 and 481.4 ms, and 320.2 ms in a run with 10 deals ahead of it; each p95 rests on only 5 calls. The cause documented on 30 September (below) fits: every request runs in a savepoint of one rolled-back transaction, and past 64 subtransactions PostgreSQL's visibility checks slow down; committed, as in production, the same calls ran flat at 341 ms p95. **Not yet re-measured committed since then**, and the database gained four indexes and the app its own login today, so it stays the write to watch: re-measure it committed, in a throwaway database, before launch or before the 25-row limit changes.

## Many people at once: the load test (12 October, item 5, D-092)

`scripts/load_test.py` (Locust) runs brands and creators through what they
really do, all at once: 16 endpoints, one write that changes nothing, each
simulated person signed in as a different seeded account so per-account rate
limits behave as they would for real people. It fails on any failed request
or any p95 over budget.

**Set-up:** one uvicorn process, as one production container runs it
(Dockerfile: one process per container). Seeded with 40 brands, 400
creators, 300 campaigns and 1,981 applications. A developer laptop under
Docker Desktop for Windows, the load generator on the same machine.

**200 people for 3 minutes: inside every budget.** 12,194 requests, none
failed, 68 a second.

| Endpoint | Requests | p95 |
|---|---|---|
| GET /campaigns/discover | 2,886 | 170 ms |
| GET /applications/me | 1,478 | 200 ms |
| GET /campaigns/discover/for-me | 1,421 | 220 ms |
| GET /deal-memos/mine | 1,171 | 170 ms |
| GET /me/attention | 984 | 210 ms |
| GET /creators/by-handle/{handle} | 978 | 130 ms |
| GET /creators/me/availability | 488 | 160 ms |
| PUT /creators/me/availability | 488 | 150 ms (budget 500) |
| GET /campaigns/{id}/summary | 433 | 220 ms |
| GET /campaigns | 420 | 180 ms |
| GET /creators (search) | 342 | 180 ms |
| GET /campaigns/{id}/applications | 327 | 220 ms |
| GET /notifications/unread-count | 232 | 150 ms |
| GET /payments/mine | 222 | 160 ms |
| GET /payments/mine/totals | 222 | 130 ms |
| GET /campaigns/{id}/report | 102 | 220 ms |

At 50 people every p95 was 43 to 170 ms (17 requests a second).

**400 people: one process falls over, and does not recover by itself.**
About 14% of requests failed with a 500 and some waited 90 seconds. The cause
is in the server log: `QueuePool limit of size 5 overflow 10 reached,
connection timed out, timeout 30.00`.

- A process has 15 database connections and up to 40 worker threads.
- A request takes its connection in the sign-in check, then waits for a
  thread to run the endpoint, while every thread waits for a connection.
- Nothing moves until a 30-second timeout fires and answers 500.
- After the load stopped, all 15 connections sat "idle in transaction" and
  even `/healthz` stopped answering. In production the container's health
  check would fail and ECS would restart it after about a minute and a half,
  dropping whatever was in flight.

**Fixed the same day (item 5a, D-093):** at most 12 requests in flight per
process, fewer than its 15 connections, so the freeze cannot form; a request
that finds no place within a second gets 503 "busy" with `Retry-After`.
Measured again, one process, same laptop:

| People | Requests in 3 min | Errors | Turned away busy | Aggregate p95 | After the load |
|---|---|---|---|---|---|
| 200 (before) | 12,194 | 0 | — | 190 ms | — |
| **200 (after)** | **12,394** | **0** | **0** | **62 ms** | — |
| 400 (before) | 812, then frozen | 14% (500s) | — | 61 s | stuck until restarted |
| **400 (after)** | **23,691** (133/s) | **0** | **2 (0.01%)** | **180 ms** | `/readyz` in 16 ms |
| **800 (after)** | **39,208** (218/s) | **0** | **48%, each within about 1 s** | **1 s** (the queue wait) | `/readyz` in 25 ms |

The 800-person run used 200 brands and 900 creators, so no account
exceeded its own rate limit.

Capping concurrency also made the normal case faster: at 200 people the
aggregate p95 fell from 190 to 62 ms, because the database is no longer
contended by more queries than it has connections.

**Honest capacity now:** one process serves about 130 requests a second
inside every budget (about 400 active people). Past that it turns the excess
away quickly and stays up. More people means more containers, and infra
does not add them by itself yet: it runs a fixed number (`api_desired_count`,
1 by default). Autoscaling on request count is a follow-up proposal
(infrastructure gate).

**Tracing costs little (D-094).** 200 people for 2 minutes, one process, on
the larger seed (200 brands, 900 creators, 600 campaigns, 3,986
applications), with a local Jaeger receiving the spans:

| Tracing | Requests | Median | Aggregate p95 | Failed |
|---|---|---|---|---|
| Off | 7,942 | 47 ms | 200 ms | 0 |
| 10% of requests (the default) | 7,941 | 46 ms | 230 ms | 0 |
| Every request | 8,004 | 51 ms | 220 ms | 3 turned away busy |

The spread is within run-to-run noise, and every endpoint stayed inside its
budget in each. The higher figures than at 200 people above come from the
larger seed, not from tracing.

**Two lessons from the first run, now in the script:**

- On Windows, `localhost` tries IPv6 first and waits about two seconds before
  falling back. Every new connection showed as a two-second request; use
  `127.0.0.1`.
- A creator's Passport is public only when published, so the test visits
  only published ones. Its 404s were correct answers.

## Added 30 September: creator search and reports

Built after the 26 September run, so measured separately: same seed (200
creators, 94 with a published Passport, 958 packages), 100 runs per read, 30
reports, one run on the same laptop.

| Endpoint | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- |
| `GET /creators` (search, no filter) | 12.7 | 16.6 | 300 | OK |
| `GET /creators?niche&city` | 14.0 | 17.1 | 300 | OK |
| `GET /creators?platform&followers` | 15.4 | 19.8 | 300 | OK |
| `GET /creators?max_price&format` | 15.3 | 23.4 | 300 | OK |
| `GET /creators?q` (words) | 14.2 | 18.6 | 300 | OK |
| `POST /reports` | 12.7 | 15.2 | 500 | OK |

Search is the query a brand runs most, and every shape of it uses under a
tenth of the read budget. The same run re-measured every endpoint below; all
stayed inside budget and close to the 26 September figures.

**One number looked worse and was not.** The bulk mark-paid read 357 ms p50
and 459 ms p95 in that run, against 289 and 314 on 26 September. Twenty
rounds showed each call slower than the last: 292 ms rising to 477 ms. The
cause is the measurement, not the code. Every request in the script runs in
a savepoint of one transaction that is rolled back, and each bulk row adds a
savepoint of its own, so the rounds pile hundreds of subtransactions into one
transaction; past 64, PostgreSQL's visibility checks slow down. The same 20
rounds with every request committed, as in production, in a throwaway
database since deleted, stayed flat:

| Bulk mark-paid, 25 rows, 20 rounds | p50 ms | p95 ms | Range ms |
| --- | --- | --- | --- |
| Inside one rolled-back transaction | 379 | 477 | 291–477, rising |
| Each request committed | 283 | 341 | 269–341, flat |

The script keeps 5 rounds, and says why next to `BULK_ROUNDS`.

## Matching, both directions (30 September)

Measured after `scripts/refresh_embeddings.py` built real Qwen3 vectors for
the seed (94 published creators, 150 campaigns). 100 runs each; each case
uses the creator or campaign with the most candidates.

| Endpoint | Candidates | p50 ms | p95 ms | Budget | Verdict |
| --- | --- | --- | --- | --- | --- |
| `GET /campaigns/discover/for-me`, creator with an embedding | 18 | 19.7 | 39.7 | 300 | OK |
| `GET /campaigns/discover/for-me`, creator without one | 19 | 19.4 | 27.7 | 300 | OK |
| `GET /campaigns/{id}/matches` (brand) | 20 | 31.5 | 50.6 | 300 | OK |

**Ranking by embeddings first cost 4 times more than not ranking:** 81 ms p50
and 101 ms p95 for the creator's list, on only 18 rows. The code fetched the
1,024-number vector into Python and sent it back as a query parameter, and
that round trip alone took about 50 ms. Reading the vector inside the query
takes about 1 ms. Both directions now do that, and ask first only whether a
vector exists. The brand side had the same pattern: 59.6 ms p95 on
25 September.

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

- **Everything built from 8 to 10 October 2026**:
  - availability (D-083);
  - invitations and repeat deals (D-084);
  - UPI pay details (D-085);
  - blocking (item 59).

  The block check also adds a condition to every search, discovery and matching query, so **the search, discovery and matching figures above predate it** and must be measured again before anyone relies on them. Query-count tests prove none of these adds a query per row; only a timed run proves they stay inside the budget.
- **Writes beyond the deal, disputes, bulk mark-paid, the rate card and
  reports.** Profile and campaign edits are single-row writes of the same
  kind, but they are not in the script yet.
- **The admin side** (D-061). Admins are few and their screens are not on a
  user's path; the report queue and account lookup are the ones to add when
  the pilot has admins.
- **Under load, on real hardware.** The load test exists (above) and was run
  on a laptop with the load generator on the same machine. A staging run
  against the real database, from another machine, is owed once AWS is up.
- **At real scale.** 150 campaigns is a pilot-sized seed, not a year of
  trading. The figures say the queries are not accidentally quadratic; they
  do not say what happens at a hundred times the rows.
- **Anywhere but a laptop.** Hosting is chosen (AWS Mumbai, D-062) but not
  yet deployed, so there is no staging number. A managed database across a
  network will not look like this.

## Running it yourself

The load test:

```powershell
uv run python scripts\seed_dev_data.py --reset --brands 40 --creators 400 --campaigns 300 --applications 2000
uv run uvicorn app.main:app --no-server-header
uv run --group load locust -f scripts/load_test.py --headless --host http://127.0.0.1:8000 --users 200 --spawn-rate 25 --run-time 3m
```

One endpoint at a time:

```powershell
docker compose up -d
uv run alembic upgrade head
uv run python scripts\seed_dev_data.py
uv run python scripts\measure_performance.py --runs 100 --deals 30
```

Add `--explain` to see the query plans behind each endpoint and confirm the
indexes are used.

## Creator search at 10,000 creators

`GET /api/v1/creators`, measured on 27 September with **10,000 extra published
creators and 34,920 packages** inserted inside a transaction and rolled back
afterwards, 30 runs per search:

| Search | p50 ms | p95 ms | Budget |
| --- | --- | --- | --- |
| No filters | 17.7 | 19.5 | 300 |
| Niche and city | 16.0 | 22.7 | 300 |
| Instagram, 10k to 50k followers | 18.7 | 29.8 | 300 |
| Reels under ₹10,000 | 32.2 | 37.6 | 300 |
| All of those together | 32.6 | 37.0 | 300 |
| Words in handle, name or bio | 39.0 | 60.6 | 300 |

No index was added: the slowest, a word search with no text index, uses a
fifth of the budget at fifty times the pilot's size. **Trigger for a trigram
index on the searched text:** a measured word-search p95 above 150 ms, or
100,000 published creators. It would be a migration, so it needs its own
approval.
