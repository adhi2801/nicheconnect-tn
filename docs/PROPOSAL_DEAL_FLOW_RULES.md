# Proposal: four rules for deliverables, payment and campaign completion

**Status: Proposed. Nothing here is built and none of it is a decision yet.** Written 4 October 2026 from a design session with one founder (the design lead, Erode Harish's track) while writing `docs/design/boarding-pass-spec.md`. **Not reviewed by a second person** (D-051).

**What this asks of Adhi.** The four product rules below were stated by a founder in that session. They change payment logic and the schema, both of which CLAUDE.md section 5 gates, and the backend is Adhi's to approve (D-051). Approve, change or refuse each one; approved ones become entries in `docs/DECISIONS.md` in the same commit as the work (section 10). Entry numbers are left as `D-0xx`: this branch's log skips D-058 and D-059, so assign numbers on approval to avoid a clash.

**Migrations.** B7 and B8 below share one migration. Only one new migration may be in flight at a time (CLAUDE.md section 1).

---

## 1. What the rules are, and what the code does today

| # | Rule (founder, 4 Oct 2026) | Today |
|---|---|---|
| 1 | No advance payment. One payment, for the full fee, after approval | Matches. One `payment_status` row per memo, due 7 days after approval (D-027) |
| 2 | Payment opens only when **every** deliverable is approved | **Does not match.** `approve_proof` calls `open_on_approval`, which opens the payment at the **first** approved proof. `deliverables` is free text with no count |
| 3 | The creator submits a **draft**; the brand approves it; the creator posts and submits the live link; the brand approves it | **Not built.** A proof is only the live link. D-026 already expects a draft to set "work started", but the code sets it only on a proof |
| 4 | A campaign is **Complete** only when every deal on it is finished | **Not built.** `close` means "stops new applications", is final, and never looks at deals. Campaign statuses are `draft`, `open`, `closed`, `cancelled` |

Constraint 1 (no funds) is untouched by all four: the brand still pays the creator directly and we record it.

---

## 2. Decisions needed

```
DECISION NEEDED 1: There is no advance payment (confirms D-027)
Context:      The design system ships an `advance_paid` status pill and an "advance"
              note on its money component. The founder says there is no advance.
Option A:     No advance. One payment for the full fee after approval, as built
              | + nothing to build; consistent with D-027 | − a brand cannot record
                  paying part up front | effort S (design system only)
Option B:     Advance plus balance: a second payment record for the advance, marked
              paid by the brand and confirmed by the creator, then the balance
              | + matches how some brands pay | − new rows, new states, new reliability
                  rules; the unique index on payment per memo no longer holds | effort L
Recommended:  A. It is what the founder chose, and it is already the behaviour.
Risk & rollback: None to the backend. The design system's `advance_paid` and the
              "advance" example are removed so a screen cannot show a state that
              cannot exist.
→ Approve A, B, or modify?
```

```
DECISION NEEDED 2: Payment opens only when every deliverable is approved (amends D-027)
Context:      A memo asking for three reels would owe the full fee after reel one.
              Rule 3 also needs each draft and live link tied to one deliverable.
Option A:     A `deal_memo_deliverable` table, one row per deliverable (title, platform,
              format, due date optional); each proof points at one deliverable;
              payment opens when all deliverables have an approved live submission
              | + one rule, enforced by the database; "2 of 3" is a count of rows;
                  each deliverable can have its own draft and live cycle
              | − the largest change; memo creation needs a list, not a text box
              | effort L
Option B:     A `deliverable_count` integer on the memo; proofs stay a flat list;
              payment opens when approved live proofs reach the count
              | + one column | − a proof is not tied to a deliverable, so "which reel
                  is this draft for?" has no answer and a draft cycle per deliverable
                  cannot be expressed. Rule 3 then fails | effort M
Option C:     Leave payment opening at the first approval
              | + nothing to build | − contradicts the rule; the full fee falls due
                  after one of three deliverables | effort none
Recommended:  A. B cannot carry rule 3, so choosing B would force a second change later.
Tables affected: deal_memo_deliverable (new); deliverable_proof gains deliverable_id
              (foreign key, indexed, per database.md); deal_memo keeps `deliverables`
              text as the brief's wording
Migration:    one, shared with Decision 3: "add memo deliverables and proof kind"
Rollback:     downgrade drops deliverable_id and the new table. Per-deliverable
              grouping is lost; the proofs themselves stay
Data impact:  existing memos have no deliverable rows. Assumed pre-launch with no live
              deals; confirm. If any live deal exists, each needs one backfilled row
              or it can never open payment. Approval for existing proofs: backfill
              one deliverable per memo and point its proofs at it
Open:         `content_due_on` is one date per memo. A date per deliverable is not
              proposed here; say if wanted.
→ Approve A, B, C, or modify?
```

```
DECISION NEEDED 3: Draft first, then the live post (extends D-024, D-025, D-026)
Context:      The creator submits a draft; the brand approves it; the creator posts
              and submits the live link; the brand approves the live work. D-026
              already says the first draft, script or proof marks work as started.
Option A:     A `kind` on each submission (`draft` or `live`). A live link is accepted
              only after that deliverable's draft is approved. A revision request at
              either step sends that one deliverable back one step. The "work started"
              marker is set by the first draft | + one rule, matches D-026 as written
              | − two new attention kinds ("review draft", "submit draft") and two
                  notification types | effort M
Option B:     Keep live-only proof
              | + nothing to build | − brand cannot veto a post before it goes live
Recommended:  A.
Sub-decision 3a, does an unreviewed draft approve itself?
  Option i:   Yes, after the same 7 days as live work (D-025), recorded as
              `auto_approved`, with the day-3 reminder
              | + a creator never waits forever, which is D-025's own reason
              | − a creator may post after silence and the brand may still dislike it
                  (the live link is still the brand's to approve or send back)
  Option ii:  No. A draft waits for the brand until it acts
              | + a draft approval always means someone looked | − a creator can be
                  blocked indefinitely, which D-025 exists to prevent
  Recommended: i. This reverses the design spec's earlier suggestion; the reason is
              D-025's. Auto-approval of a draft never replaces approval of the live work.
Tables affected: deliverable_proof (+ kind, CHECK in ('draft','live')); the
              attention kinds and notification types lists
Migration:    the same one as Decision 2
Rollback:     downgrade drops `kind`. Existing proofs become unlabelled; they were
              all live links, so the backfill is `live`
Data impact:  existing proofs backfill to `live`
→ Approve A or B, and 3a (i or ii)?
```

```
DECISION NEEDED 4: A campaign is "Complete" when every deal on it is finished
Context:      The founder wants completion tied to delivery. `close` today means
              "stop taking applications" and cannot be undone.
Option A:     Keep `close` as it is. "Complete" is worked out, not stored: a campaign
              is Complete when it is `closed`, has at least one deal, and every deal
              on it is finished (payment confirmed, or barter and all approved, or
              declined, or cancelled). A per-campaign summary endpoint returns deals
              by stage and the flag
              | + no new status, no migration for the flag; a brand can still stop
                  taking applicants; consistent with D-033 (derive, do not store)
              | − one more endpoint | effort M
Option B:     `close` itself requires all deals finished
              | + one concept | − a brand cannot stop applications while a creator
                  is mid-delivery, which blocks the common case. Also changes the
                  meaning of an existing endpoint | effort M
Recommended:  A.
Risk & rollback: Additive endpoint only; remove it to roll back.
Open:         Whether a deal with a creator's payment `unconfirmed` counts as finished
              (boarding pass spec, question 2). Proposed: yes for the campaign, since
              the brand has nothing left to do and the creator's silence cannot hold
              a campaign open, consistent with D-034 point 1.
→ Approve A, B, or modify?
```

---

## 3. Not decided here (so they are not decided by accident)

1. **A deliverable that never arrives.** What happens to the other deliverables and to the fee? D-026 covers cancelling a whole deal, not part of one. This needs its own decision before partial delivery is built.
2. **Per-deliverable due dates.** One `content_due_on` per memo today.
3. **Proof media.** D-024 requires a screenshot or recording as well as the link; the proof response carries neither. Unchanged by this proposal.
4. **A public "verify this deal" code.** The deal record is for the two parties only; sharing it is a separate privacy decision (boarding pass spec, question 3).

## 4. If approved, the order of work

1. Design system: remove `advance_paid` and the "advance" example (no backend). Decision 1.
2. One migration for Decisions 2 and 3, with a working downgrade and a test run against real Postgres (`docs/standards/database.md`).
3. Service rules and tests for Decisions 2 and 3: payment opens only when all deliverables are approved; no live link before an approved draft; draft auto-approval per 3a.
4. Campaign summary endpoint for Decision 4, then `openapi.json` regenerated and the contract tests re-run.
5. Boarding pass spec updated from "intended" to "built", and the brand campaign board spec written against the summary endpoint.

Each step is one file at a time and its own commit, on its own branch, with a pull request. While Adhi is the only builder, say in each pull request that it has not had a second pair of eyes (CLAUDE.md section 0).
