# Checking a deal record yourself

Every deal on the platform has a record: each step (sent, accepted, work
submitted, paid, and so on) is an entry, and each entry is **sealed** with a
SHA-256 fingerprint that covers the entry before it. If anyone changes,
removes or reorders an entry, the seals stop matching (D-057).

We check the seals ourselves and report the result as `intact`. **You do not
have to take our word for it.** This page shows how to check them with
nothing but the record and Python's standard library.

## 1. Get the record

Either of these works:

- `GET /api/v1/deal-memos/{memo_id}/record`, as the brand or the creator of
  that deal; or
- your data export (`GET /api/v1/me/export`), section `deal_record`, which
  holds the same entries for every deal you are part of.

**Keep `latest_seal`.** It is the one number that lets you catch a rewrite
later (section 4).

## 2. How each seal is made (version `deal-record/v1`)

For each entry, in order of `sequence`:

1. Build this object from the entry:

   ```json
   {
     "deal_memo_id": "...",
     "sequence": 1,
     "kind": "memo_sent",
     "actor_role": "brand",
     "actor_account_sha256": "...",
     "occurred_at": "2026-09-26T06:30:00.000000Z",
     "recorded_at": "2026-09-26T06:30:00.000000Z",
     "facts": { }
   }
   ```

   Copy every value exactly as it appears. The times are already in the
   spelling the seal uses: UTC, to the microsecond, ending in `Z`.

2. Turn it into bytes: JSON with **keys sorted at every level, no spaces**,
   UTF-8. (This is RFC 8785's canonical form for these values. The record
   never contains decimals, so there is only one way to write it.)

3. The seal is `SHA-256( "deal-record/v1\n" + previous_seal + those bytes )`,
   where `previous_seal` is the previous entry's seal as **32 raw bytes**
   (for the first entry, 32 zero bytes).

Each entry's `previous_seal` must equal the previous entry's `seal`, and its
own `seal` must equal what you computed.

## 3. A script that does it

Save the record response as `record.json` and run this. It needs nothing
except Python 3. It works on the export's rows too: they carry their own
`deal_memo_id`, and their times are in the seal's spelling.

```python
import hashlib
import json

record = json.load(open("record.json", encoding="utf-8"))
# From the record endpoint: record["entries"]. From an export file: the rows
# of data["deal_record"] that share one deal_memo_id.
entries = record["entries"]

previous = "00" * 32
for entry in sorted(entries, key=lambda e: e["sequence"]):
    body = {
        "deal_memo_id": entry.get("deal_memo_id") or record["deal_memo_id"],
        "sequence": entry["sequence"],
        "kind": entry["kind"],
        "actor_role": entry["actor_role"],
        "actor_account_sha256": entry["actor_account_sha256"],
        "occurred_at": entry["occurred_at"],
        "recorded_at": entry["recorded_at"],
        "facts": entry["facts"],
    }
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    seal = hashlib.sha256(
        b"deal-record/v1\n" + bytes.fromhex(previous) + canonical
    ).hexdigest()
    if entry["previous_seal"] != previous or entry["seal"] != seal:
        raise SystemExit(f"Entry {entry['sequence']} does not match.")
    previous = seal

print("Every seal matches. Latest seal:", previous)
```

The same check runs in our test suite, against real deals, on every change
(`test_the_seals_check_out_from_the_json_alone`).

## 4. What the seals prove, and what they do not

**They prove** the record has not changed since you last saw it, *if* you
kept the `latest_seal` you saw then. Recompute, and compare the seal at that
same entry with the one you kept.

**Our `intact` alone cannot prove** that we did not rebuild the whole record
and seal it again. Only a seal you saved, or step 2's daily outside
timestamps (not yet built), can show that. We say so because it is true.

## 5. Reading the facts

Figures appear as they are: amounts in paise, dates, statuses. **Anything a
person typed appears only as a SHA-256 fingerprint** (a field ending in
`_sha256`): the memo's terms, the proof link, notes and payment references.
To show that a fingerprint matches what you hold, hash your copy:

```python
import hashlib

hashlib.sha256("412345678901".encode("utf-8")).hexdigest()
```

`terms_sha256` covers the memo's terms, in this exact object, canonicalised
as in section 2: `deliverables`, `fee_amount_paise`, `currency`,
`cancellation_fee_paise`, `approval_window_days`, `payment_due_days`,
`usage_rights_days`, `content_due_on` (as `YYYY-MM-DD`), `disclosure_required`
and `extra_terms`.

`actor_account_sha256` is the fingerprint of the acting account's id. Hash
your own account id the same way to find the entries you made. The other
side's account id is not shown to you, and it cannot be worked out from its
fingerprint.

## 6. Using it as evidence

Section 63 of the Bharatiya Sakshya Adhiniyam, 2023 asks for the hash value
of an electronic record produced in evidence, with the algorithm used. The
record gives you SHA-256 values for every step. **Whether that is enough in a
particular case is a legal question** for your lawyer; we do not claim it is.
