# Proposal: the job runner, and a daily outside timestamp on every deal record

**Status: proposed, not built.** Written 26 September 2026 on
`feature/record-anchoring`, stacked on `feature/deal-record`. It needs five
approvals, listed in section 5.

## 1. Why these two together

**The job runner is the backend's biggest missing piece that no vendor
blocks.** Four things wait on it: delivering notifications (E1, which also
needs a provider), usage-rights reminders (C5), proof link re-checks (D-024),
and step 2 of the deal record. D-047 locked DBOS as the runner, "installed
with the first background job". This proposes that first job.

**The first job should matter, and should need no outside account.** Step 2
of the deal record fits both. Step 1 (D-057) left one gap, and said so:
*someone with full control of our database can rebuild a whole record and
reseal it, and only a party who saved an earlier seal would notice.* A daily
outside timestamp closes that gap for everyone, including parties who never
saved anything.

## 2. What it does

Once a day, just after midnight in Tamil Nadu:

1. **One fingerprint covers every deal.** Take each deal's latest seal as of
   midnight and build a **Merkle tree** over them. A Merkle tree is a hash of
   hashes, and it is what Certificate Transparency uses to keep every HTTPS
   certificate public. The tree's root is one SHA-256 value that depends on
   every seal in it.
2. **Two independent authorities timestamp that root.** An RFC 3161
   timestamp authority signs "this value existed at this time" with its own
   key. We ask two, run by different companies (DigiCert and Sectigo), so no
   single outage or compromise matters. Both are free, and the request
   carries only the root, which reveals nothing about any deal.
3. **We store the root and both signed timestamps**, in two new append-only
   tables.

Then any party can ask for **their deal's proof for a day**: the root, the
signed timestamps, and the handful of sibling hashes that connect their deal's
seal to the root. With that, anyone can show that the seal existed on that
day, **using the timestamp authority's signature rather than ours**. From
then on, rewriting that deal's history would mean forging DigiCert's and
Sectigo's signatures.

**What it adds for a creator chasing an unpaid fee:** a record whose date
does not rest on our word. **What it costs:** two small HTTPS requests a day,
and no per-deal cost.

## 3. How it is built

- **DBOS runs inside our app**, not as a separate service. It keeps its own
  job state in Postgres, so this adds no broker, no worker fleet and no
  new deployable, and it fits the scale posture (`CLAUDE.md` section 3). A
  scheduled workflow runs the daily step. Each step is checkpointed, so a
  crash halfway resumes rather than repeating, and two app instances do
  not both run it.
- **Timestamp requests** use `httpx2`, already in the stack, with the timeouts
  and backoff `backend.md` requires. **Verifying** a timestamp's signature
  uses `rfc3161-client` from Trail of Bits. It is small, Apache-licensed and
  focused on exactly this job; hand-parsing signed ASN.1 would be a security
  mistake.
- **The tree** follows RFC 6962 (Certificate Transparency's hashing rules), so
  standard tools and papers apply. It is about 40 lines of `hashlib` and needs
  no dependency.
- **The leaves need no storage.** The record is append-only, so "each deal's
  latest seal as of midnight" can always be recomputed exactly. We store only
  the root, the cut-off time, the leaf count and the signed timestamps.

### New tables (schema request)

```
deal_record_checkpoint          one row per day
  id              UUID, uuidv7()
  covers_until    TIMESTAMPTZ, UNIQUE      midnight IST, as UTC
  leaf_count      INTEGER, >= 0
  merkle_root     BYTEA, exactly 32 bytes
  created_at      TIMESTAMPTZ
  append-only by trigger, like deal_record_entry

deal_record_timestamp           one row per authority per checkpoint
  id              UUID, uuidv7()
  checkpoint_id   UUID, FK -> deal_record_checkpoint, ON DELETE RESTRICT
  authority       VARCHAR(40), CHECK in ('digicert', 'sectigo')
  token           BYTEA                    the signed RFC 3161 response, as issued
  signed_at       TIMESTAMPTZ              the authority's time, read from the token
  UNIQUE (checkpoint_id, authority)
  append-only by trigger

Migration:   one revision. No existing table changes.
Rollback:    downgrade drops both tables and their triggers.
Data impact: about 1 row plus 2 tokens (~5 KB each) a day; about 4 MB a year.
```

The same two named departures as D-057, for the same reasons: no
`updated_at`, and an append-only trigger.

### New endpoint

`GET /api/v1/deal-memos/{id}/record/proof?date=YYYY-MM-DD` returns the
root, the leaf index, the sibling hashes and both tokens (base64), for the
deal's two parties only. `docs/DEAL_RECORD_VERIFY.md` gains a section showing
how to check it with `openssl ts -verify`, which ships with most systems, so
the check needs no code of ours at all.

## 4. What it defends against, completed

| Threat | Step 1 (built) | With this |
|---|---|---|
| A bug or script rewrites history | Refused by the database | — |
| Terms changed after acceptance | Detected | — |
| **Someone with full database control rebuilds and reseals a chain** | Caught only if a party saved a seal | **Caught for everyone, from the day after the entry**: the rebuilt seals no longer lead to a root the authorities signed |
| We backdate an entry | Not detectable | **Detectable**: an entry cannot appear in a checkpoint signed before it existed |

**Still not covered, stated plainly:** anything within the same day, before
the checkpoint runs. Hourly checkpoints would narrow that to an hour at 24
times the requests; daily is proposed for the pilot, and the interval is one
setting.

## 5. Decisions needed

```
DECISION NEEDED 1: Install DBOS as the job runner (dependency)
Package:      dbos 3.1.0 (MIT), released 24 Sep 2026, current stable
Why:          D-047 locked it; this is the first job. No broker, no new service.
Alternatives: (a) dbos 2.31.1, the last 2.x: more mileage, but a forced major
              upgrade soon after; 3.0 changed the schema. (b) Procrastinate
              (Postgres-backed queue): fewer features, no durable workflows.
              (c) No package: a cron job outside the app. That is a new
              deployable and loses checkpointing.
Security/maintenance: active weekly releases; MIT; stores job inputs in
              Postgres, so no PII may be passed to a workflow (only ids).
Recommended:  3.1.0. We start with no workflows, so 3.x costs no migration,
              and our first job is one whose failure only delays a
              checkpoint. Nothing user-facing depends on it.
→ Approve 3.1.0, 2.31.1, or another?

DECISION NEEDED 2: Where DBOS keeps its own state
Option A:     Its own schema, `dbos`, in our database. DBOS creates and
              upgrades its tables itself.
              | + how it is designed and tested | − those tables are not
              in our Alembic chain, which is one reading of constraint 3
Option B:     run_migrations=False, and we copy DBOS's DDL into our own
              Alembic migrations on every DBOS upgrade
              | + strictly migrations-only | − we would maintain another
              project's internal schema, and get it wrong on some upgrade
Recommended:  A. Constraint 3 exists so *our* schema changes are reviewed and
              reversible. DBOS's internal tables are a library's versioned
              state, like Alembic's own `alembic_version` table. Alembic does
              not look outside the default schema, so `alembic check` stays
              clean. This needs both founders if you read constraint 3
              strictly: say so, and B it is.

DECISION NEEDED 3: rfc3161-client 1.0.9 (dependency)
Package:      rfc3161-client (Apache-2.0, Trail of Bits), verifies RFC 3161
              timestamp tokens and their certificate chains
Alternatives: hand-written ASN.1 parsing (refused: a signature check is not
              where to improvise); asn1crypto plus our own logic (more code
              of ours, same risk); no verification (we would store tokens we
              never checked)
Recommended:  rfc3161-client.

DECISION NEEDED 4: The two tables in section 3 (schema request, as written)

DECISION NEEDED 5: Two outbound calls a day, to timestamp.digicert.com and
              timestamp.sectigo.com, carrying one SHA-256 value each
              (infrastructure: a new external dependency at runtime)
Recommended:  approve. If both are unreachable the day's checkpoint is
              retried the next run and the gap is recorded, never hidden.
```

**Reply "yes" to approve all five as recommended**, or name the ones to
change.

## 6. Build plan, once approved

1. `requirements.txt`: pin both packages; run pip-audit, as CI does.
2. The migration, models and model tests (CHECKs, the unique date, triggers,
   round trip).
3. `record_anchor` service: the RFC 6962 tree, with published test vectors;
   building a checkpoint; requesting and verifying tokens.
4. DBOS wired into the app's startup, with the daily scheduled workflow. Tests
   run the workflow directly, with the authorities faked at the HTTP boundary.
   One opt-in test hits the real authorities and is kept out of CI.
5. The proof endpoint, its tests, the `openssl` section of the guide, and a
   test that runs the guide's commands.
6. A decision entry, measured numbers and a report.
