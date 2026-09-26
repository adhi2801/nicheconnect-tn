# Proposal: a deal record nobody can quietly rewrite (C1)

**Status: step 1 approved and built (D-057), 26 September 2026.** Step 2
(section 4) is still a proposal. Written on
`feature/deal-record`. It stacks on `feature/fair-rate-guidance`, because the
rate card migration has not merged yet and only one migration may be in
flight at a time (`CLAUDE.md` section 1).

## 1. The problem

Every deal, proof and payment row is **updated in place**. When a status
changes, the old one is gone. When a payment reference is corrected, the
first one is gone. What was agreed survives only as the memo's current
contents, and nothing proves those contents are what the creator accepted.

That matters at exactly one moment: **when a brand and a creator disagree**.
The creator says the fee was ₹15,000 and the brand says ₹12,000. The brand
says it paid on the 3rd; the creator says no reference was given until the
10th. Today our answer is "this is what the row says now". That is not good
enough for a product whose whole promise is a record both sides can trust.
Worse, the operator (us) could change a row, and nobody could tell.

## 2. What this builds

**A per-deal record of dated facts, each entry sealed to the one before it.**

- Every step in a deal's life adds one entry: sent, revised, changes
  requested, accepted, declined or cancelled; work submitted, approved,
  auto-approved or sent back; payment opened, marked paid and confirmed;
  dispute opened, added to and closed.
- Each entry carries the **SHA-256 fingerprint of the entry before it**. Change
  any earlier entry, and every fingerprint after it stops matching.
- The entry is written **in the same database transaction** as the change it
  records, so a change without its entry cannot exist, and neither can an
  entry without its change.
- **The database itself refuses** to update or delete an entry. A trigger
  rejects `UPDATE`, `DELETE` and `TRUNCATE`, so a bug, a careless script or a
  hand-edit fails loudly instead of rewriting history (constraint 3).
- **Both parties can check it.** `GET /api/v1/deal-memos/{id}/record` returns
  the entries, the fingerprints and whether the chain is intact. The data
  export includes it. `docs/DEAL_RECORD_VERIFY.md` gives the method, so anyone
  can check it with twenty lines of Python and without trusting us.

### What goes in, and what deliberately does not

**In, as plain facts:** what happened, who did it (their role and account id),
amounts in paise, dates, statuses, the proof format, and a cancellation's kind.

**In, as fingerprints only:** everything a person *typed*, meaning the memo's
terms (deliverables, extra terms), the proof link and the payment reference.
The permanent record holds the SHA-256 fingerprint. The text stays in the
ordinary tables, where it can still be corrected or erased.

This split is the design's most important choice. A permanent record that
held typed text would permanently hold whatever someone typed into it,
including a phone number in a deliverables box, and could never honour an
erasure request. Fingerprints prove the terms have not changed without keeping
them. **Honest limit:** a 12-digit payment reference has few enough possible
values that someone with database access could work it out from its
fingerprint by trying them all. That same person can already read it in
`payment_status`, so this adds no exposure while the data exists. What
happens after an erasure is for the validation pack (section 6).

**Two times on every entry.** `occurred_at` is when it took effect, and
`recorded_at` is when we wrote it down. They differ for one case that matters:
work a brand never reviewed is approved *at the deadline* (D-025), but it is
recorded the next time anyone looks. The record shows both, rather than
pretending we noticed at the time.

## 3. The schema, for approval

```
DECISION NEEDED: the deal_record_entry table (schema request)
Tables affected: one new table, deal_record_entry. No existing table changes.

  id                 UUID, uuidv7()          new tables use UUIDv7 (D-047)
  deal_memo_id       UUID, FK -> deal_memo, ON DELETE RESTRICT
                     (a deal with a record can never be deleted out from under it)
  sequence           INTEGER, >= 1           1, 2, 3 ... within one deal
  kind               VARCHAR(40), CHECK in the list in section 2
  actor_role         VARCHAR(10), CHECK in ('brand', 'creator', 'system')
  actor_account_id   UUID NULL, no FK        'system' has none; no FK so a
                     deleted account never blocks or alters the record
  occurred_at        TIMESTAMPTZ             when it took effect
  recorded_at        TIMESTAMPTZ, now()      when we wrote it down
  facts              JSONB                   plain facts and fingerprints only
  previous_hash      BYTEA, exactly 32 bytes (all zeros for sequence 1)
  entry_hash         BYTEA, exactly 32 bytes

  UNIQUE (deal_memo_id, sequence)            two writers cannot fork a chain:
                                             the second one fails and retries
  CHECK   (sequence = 1) = (previous_hash is all zeros)
  TRIGGER refusing UPDATE, DELETE and TRUNCATE
  The UNIQUE index also serves every read (by deal, in order). No other index.

Migration:   one revision, stacked on the rate card's. Existing deals get a
             single opening entry that snapshots their current state, marked
             "record_started", so no deal pretends its history began earlier
             than it did. (Only development data exists today.)
Rollback:    downgrade drops the trigger, its function and the table. The
             record is lost; nothing else is touched.
Data impact: one small row per deal step, about 400 bytes. A busy pilot deal
             has about 10.
```

**Two deliberate departures from `database.md`, named here so they are not
silent:**

1. **No `updated_at`.** The standard asks every table for one. A row that can
   never be updated would carry a column that always equals `created_at`, and
   anyone reading it would reasonably wonder what updates it. `recorded_at`
   plays the `created_at` role.
2. **A trigger.** This is the first in the schema. It is the only way to make
   "append-only" a property of the database rather than a promise of the code.

**The fingerprint** is SHA-256 over a fixed prefix, the previous fingerprint,
and the entry in canonical JSON: keys sorted, no spaces, UTF-8, whole numbers
only, and times in UTC to the microsecond with a `Z`. For that restricted set
of values it matches RFC 8785, the JSON canonicalisation standard, so it
needs **no new dependency**. It uses Python's own `hashlib`.

## 4. What it defends against, and what it does not

| Threat | Step 1 (this proposal) | Step 2 (later) |
|---|---|---|
| A bug or script rewrites a deal's history | **Refused by the database** | — |
| Someone edits an entry by hand | **Refused**, unless they first drop the trigger | — |
| Someone with full database control rewrites a whole chain and recomputes it | **Not stopped.** A party who saved an earlier fingerprint would see the difference | Stopped: see below |
| The terms are changed after acceptance | **Detected**: the accepted entry's fingerprint no longer matches | — |

**Step 2, needing its own approval later:**

- **Signed receipts.** Each entry is signed with an Ed25519 key only the
  service holds. A party holding a receipt can then prove we recorded exactly
  that, even against us. This needs a key and its storage, which is a security
  gate.
- **Daily outside timestamps.** One fingerprint covers every deal's latest
  entry (a Merkle root, the structure Certificate Transparency uses), stamped
  once a day by independent RFC 3161 timestamp authorities. After that, even
  someone with full control of our servers cannot backdate a rewrite. This
  needs the job runner (still undecided, like C5) and one outbound call a day.

Step 1 is useful on its own, and step 2 builds on it without changing it.

## 5. Why this and not something else

- **AWS QLDB**, the managed ledger many teams used for this, was
  [shut down on 31 July 2025](https://www.infoq.com/news/2024/07/aws-kill-qldb).
  AWS's migration advice points to Aurora PostgreSQL with audit logging, which
  records changes
  [but proves nothing](https://concepttocloud.com/news/what-to-use-instead-of-aws-qldb).
  A hash chain in Postgres is the recognised replacement, and it keeps us
  inside our approved stack. A dedicated ledger database would need both
  founders (section 3 of `CLAUDE.md`), for no gain at pilot scale.
- **Indian courts are asking for exactly this.** Under
  [section 63 of the Bharatiya Sakshya Adhiniyam, 2023](https://www.scconline.com/blog/post/2026/07/13/sc-explains-electronic-evidence-rules-under-bsa-2023-clarifies-hash-value/),
  an electronic record produced in evidence comes with a certificate stating
  its hash value and algorithm. A creator chasing an unpaid fee would already
  hold SHA-256 fingerprints of every step. **Whether our export meets
  section 63 is a legal question for the validation pack.** This proposal
  makes the fingerprints exist; it does not claim they are sufficient.
- **None of the ~20 competitors** in `docs/COMPETITIVE_LANDSCAPE.md` is
  recorded as offering a deal record that either side can independently
  verify. Combined
  with the payment and delivery records (D-034, D-038), it is how "trust us"
  becomes "check for yourself".

## 6. Questions for the validation pack (constraint 6, not guessed)

1. How long must, or may, the record be kept? It holds no typed text, but it
   does hold account ids, amounts and dates.
2. After a DPDP erasure, is a permanent fingerprint of erased text acceptable,
   including the brute-force limit on payment references (section 2)?
3. What, if anything, does section 63 of the BSA require of the *platform*,
   as opposed to the party producing the record?

## 7. Build plan, once approved

1. The migration, the model, and model tests: every CHECK, the unique
   sequence, the trigger refusing `UPDATE`, `DELETE` and `TRUNCATE`, and the
   upgrade → downgrade → upgrade round trip.
2. `deal_record` service: `append()` inside the caller's transaction, and
   `verify()`. Then one call added at each of the roughly 15 transitions in the
   deal memo, proof, payment and dispute services.
3. `GET /api/v1/deal-memos/{id}/record` for both parties only. Another
   account's deal returns 404. Plus the export section and the verification
   document.
4. Tests: every transition writes exactly one entry with the right facts and
   no typed text; a failed transition writes none; a tampered entry is caught
   by `verify()`; concurrent appends cannot fork; a query count that does not
   grow; and p95 for a write with its entry, measured against 500 ms.
5. A decision entry and a report.
