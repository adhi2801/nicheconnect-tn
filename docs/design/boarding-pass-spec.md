# Boarding pass (one per deal) — design spec

**Name in the UI:** "Pass". In code and in this file: the pass is the screen for one deal memo.
**Routes:** `/deals` (the stack) and `/deals/:memoId` (one pass)
**Status:** Proposed. Design only; no frontend code exists or starts here (D-053).
**Contract checked against:** `docs/api/openapi.json` and the payment, proof and memo services, read 4 October 2026. Design system read from the published Colyv design system (README, tokens, `StageTracker`, `StatusPill`, `MoneyCell`, `ListRow`, icons).
**Not reviewed by a second person.** Written in a session with one founder present (D-051).

**Product rules given on 4 October 2026.** These are the founder's answers in a session and are **not yet entries in `docs/DECISIONS.md`**. Each changes payment logic or the schema, so each needs Adhi's approval and a decision entry before it is built (CLAUDE.md section 5):

1. **No advance.** One payment, for the full fee, after approval. There is no "balance".
2. **Payment opens only when every deliverable is approved**, not at the first approval.
3. **Draft first, then post.** The creator submits a draft; the brand approves it; the creator posts and submits the live link; the brand approves the live work.
4. **A campaign is "Complete" only when every deal on it is finished.** `close` keeps its meaning (stop taking applications).

None of 2, 3 or 4 exists in the backend today (section 9, B7 to B9). Everything below describes the intended behaviour, not the current one, and marks where the two differ.

---

## 1. Job of the pass

A creator works with several brands at once. For each brand they should be able to answer, at a glance:

1. What was agreed (fee, what to deliver, by when)?
2. Where is this deal now?
3. What, if anything, is waiting on me, and by when?
4. Has this brand paid, and did I confirm it?

One pass is one deal memo. Three brands, three passes. A brand sees the same pass for each creator it works with, with the same stages and different next actions; the brand's own overview across many creators is a separate screen and is not specified here.

It answers the two fears the design system names: *I did the work and I'm not being paid*, and *I paid for a post that never happened*. It states facts the records hold. It does not judge either side (D-028).

## 2. Words

| Term | Means | Not |
|---|---|---|
| Deal memo | The agreed terms. Not a contract, and the UI never claims legal force | "contract" |
| Pass | The screen showing one memo and where it has reached | A second record. It stores nothing; everything on it is read from the API |
| Stage | A step the deal has reached, worked out from several records (section 4) | A field the API returns. **No `stage` field exists** (section 9, request B1) |

## 3. When a pass exists

A creator can read a memo only once the brand has **sent** it; drafts are not theirs to see (`GET /deal-memos/{id}`). So:

- **Before the memo is sent** (application accepted, memo still a draft): no pass. The creator sees the application in "My applications" with the words the API has (`accepted`). Nothing says "your pass is coming".
- **From `sent`:** the pass exists and opens at the first stage.
- A brand sees the pass from `draft`, because drafts are theirs.

Recommended: issue the pass at **memo sent**, not at "campaign starts". Reason: that is the first moment both sides can see the same terms. Open question 1.

## 4. Stages

A pass is a left-to-right strip. Stages are **worked out from the memo, its deliverables and their proofs, the payment and any dispute**, and never stored. Every stage pill carries a word and an icon (design system). Status colour follows the tokens: success for done, warning for waiting, danger for a problem, neutral otherwise; `brand-primary` is for actions only and is never a status colour.

| # | Stage (words on the pass) | True when | Who acts next | Date shown |
|---|---|---|---|---|
| 1 | **Memo sent** | `memo.status = sent` | Creator: accept, ask for a change, or decline | `sent_at` |
| 1a | **Changes requested** | `memo.status = change_requested` | Brand: revise and send again | When asked (see gap B4) |
| 2 | **Agreed** | `status = accepted`, no proof yet | Creator: submit the work | `accepted_at`; due `content_due_on` |
| 3 | **In progress, {n} of {total} approved** | `status = accepted` and fewer than all deliverables approved | Whoever the current deliverable is waiting on (see below) | Next date that applies |
| 4 | **Payment** | Every deliverable is approved and a payment record exists (it opens on the last approval, never for barter). For barter, "All approved" is the end | Brand: mark as paid. Creator: confirm | Date of the last approval (say "Approved automatically on {date}" when `auto_approved`), then `due_on`, `marked_paid_at`, `confirmed_at` |
| 5 | **Finished** | Payment `confirmed`, or barter and all approved | Nobody | `confirmed_at` or the last approval |

Stage 5 has its own sub-states, read straight from `payment.state` (a value the API works out from dates):

| `payment.state` | Words | Tone |
|---|---|---|
| `due` | "Payment due {due_on}" | warning |
| `late` | "Payment {days_overdue} days late" | danger |
| `unpaid` | "Not paid, {days_overdue} days past due" | danger |
| `paid` | "{Brand} marked this paid on {marked_paid_at}. Waiting for {creator} to confirm." | warning |
| `unconfirmed` | "{Brand} marked this paid on {date}. {Creator} has not confirmed." | neutral |
| `confirmed` | "{Creator} confirmed receipt on {confirmed_at}" | success |

`unconfirmed` is not a finding against anyone. It states that the brand says it paid and the creator has not answered after seven days (the service says so in the same words). Never colour it danger.

### Inside stage 3: each deliverable has its own four steps

A memo can ask for several deliverables ("3 reels"). The strip describes the **deal**; each deliverable has its own small sequence, shown in the Work section (section 5) and summarised on the front as "2 of 3 approved".

| Step | Who acts | Words |
|---|---|---|
| Draft | Creator submits a draft; brand approves it or asks for a revision | "Draft submitted", "Draft approved", "Draft needs changes" |
| Live work | Creator posts and submits the live link; brand approves it or asks for a revision | "Live link submitted", "Approved", "Live work needs changes" |

The order is fixed: **no live link is accepted before the draft is approved.** Payment never opens until every deliverable has reached "Approved". A revision request at either step sends that deliverable back one step and nothing else.

Today's backend has one flat list of proofs per memo, no deliverable count and no draft step (B7, B8). Until they exist, a pass cannot truthfully say "2 of 3".

### Branches and endings

The strip is a straight line. These are not stages; they are shown as one extra pill next to the stage they interrupt.

| Situation | Source | Pill words | Tone |
|---|---|---|---|
| Dispute on the payment | `payment.has_open_dispute`; `dispute.state` | "Disputed, response due {response_due_on}" while `open`; "Unresolved after 30 days" when `unresolved`; the outcome in words when `resolved_*` | danger, then neutral once resolved |
| Declined | `memo.status = declined` | "Declined by {creator}" | danger |
| Ended before any work | `cancellation_kind = withdrawn_early` | "Ended before any work was submitted" | neutral |
| Cancelled after work | `cancelled_by_brand` / `cancelled_by_creator` | "Cancelled by {brand or creator} on {cancelled_at}"; if `cancellation_fee_paise` is above zero, "Cancellation fee ₹{amount}" as a fact | danger |

An ended deal keeps its pass, read-only, in the stack's "Finished" group.

**Do not** draw "work started" as a stage. `work_started_at` is set at the first proof submission, not at acceptance; it exists to decide whether a cancellation counts (D-026). A creator who accepted and has not submitted anything is at "Agreed".

**Do not** use `advance_paid` or any status the API lacks. The design system's `StatusPill` map includes `advance_paid` and its `MoneyCell` example says "advance"; the founder has decided there is **no advance**, so both are wrong for this product. Use only the words above (section 9, request B5).

## 5. What one pass shows

360 px wide first. One column; the strip scrolls inside its own container if needed, never the page.

### Front (always visible)

| Element | Source | Format |
|---|---|---|
| Counterparty | For a creator: the brand. For a brand: the creator's `@handle` (`counterparty` in the attention list) | Third person: "Waiting on Priya" |
| Campaign title | `campaign_title` (attention) | `headline` |
| Fee | `fee_amount_paise`, `currency` | `MoneyCell`, whole rupees, Indian grouping, ₹8,000. **Null means barter**: show "Barter deal, no fee". Never ₹0 |
| Deliverables | `deliverables` (text today) and, once B7 exists, a count | As written, `callout`, then "2 of 3 approved". Without the count, show no fraction rather than guessing one |
| Due date | `content_due_on` | "Content due 12 Oct 2026". Dates as `23 Sep 2026` |
| Disclosure | `disclosure_required` | "Disclosure required" or omit when false |
| Stage strip | Section 4 | `StageTracker` plus the branch pill |
| Current line | Section 4 table | One sentence: who acted, when, what happens next |
| Next action | `GET /me/attention`, matched on `memo_id` | One primary button, when something waits on the signed-in person. Otherwise "Waiting on {counterparty}", no button |

The one primary action rule holds: a pass has at most one primary button.

### Back (opens below the front, or a second tab)

| Section | Source | Notes |
|---|---|---|
| Terms | `extra_terms`, `usage_rights_days`, `approval_window_days`, `payment_due_days`, `revision_count`, `cancellation_fee_paise` | Omit what is null. `usage_rights_days` null: omit the line (open question 4 in the Passport spec applies) |
| Work | `GET /deal-memos/{id}/proof` | One block per deliverable with its own four steps (section 4). Each submission: format, link, note, `disclosure_confirmed`, status, `revision_note`. Today the list is flat and newest first, with no draft and no deliverable grouping |
| Payment | `GET /deal-memos/{id}/payment` | Amount, `due_on`, method, reference (UPI reference as `code` type), who marked and who confirmed, each with a date. Facts only |
| Dispute | `GET /deal-memos/{id}/payment/dispute` | Timeline of `opened`, `response`, `evidence`, `closed` |
| Deal record | `GET /deal-memos/{id}/record` | The sealed history (below) |

### The deal record, honestly

- The record lists every step with a date, who acted (`brand`, `creator`, or `system` for the deal's own rules such as approval at the deadline) and a seal tying it to the one before. It shows typed text only as a fingerprint.
- Show: the entry count, `intact` ("The record holds together" or "An entry does not match, from step {n}"), `terms_unchanged_since_accepted`, and a **copy button for `latest_seal`** so a party can keep it and later catch a rewrite.
- **Both endpoints (`/record` and `/record/proof`) are for the brand and the creator on the deal only.** The pass must not offer a public "verify this deal" code or link. A third party cannot call it. If a shareable proof is wanted, that is a backend request and a privacy decision (open question 3).
- Say "intact" as our own check, with a link to `docs/DEAL_RECORD_VERIFY.md`. Never "verified" or "guaranteed" (D-055).
- Daily proof (`/record/proof`): show "Tied to the checkpoint of {checkpoint_date}" when `stamped` is true. When false, show the gap plainly: "Not yet stamped". A 409 means the record no longer matches a stamped checkpoint; show it as a plain statement with the request ID, no alarm wording.

## 6. The stack (`/deals`)

The creator's home for deals: one row per pass, using `ListRow` (leading: stage pill; title: brand and campaign; subtitle: the current line; trailing: `MoneyCell` and due date).

Groups, in this order:

1. **Needs you.** Passes with an item in `GET /me/attention`. Order is the API's own: overdue first, then soonest due, then undated. Do not re-sort.
2. **Waiting on others.** In progress, nothing for you to do.
3. **Finished.** Collapsed. Ended, declined and finished passes.

Groups 2 and 3 need each pass's stage, and `GET /deal-memos/mine` returns only the memo, not the proof or payment. See request B1; until it exists this screen costs one or more extra calls per row, which `ux.md` section 7 says to raise rather than accept.

For a creator the stack is a list, not a card pile: tight rows, air from spacing (design system "density with air"). The UI calls it "Your deals".

## 7. States

| State | Trigger | What is seen | Primary action |
|---|---|---|---|
| Loading | Request in flight | Skeleton of the front and strip. The one skeleton pulse only | none |
| Normal | 200 | Sections 4 and 5 | The next action, if any |
| Empty stack | No memos | "No deals yet. When a brand sends you a deal memo, it appears here." | "Browse open campaigns" |
| Waiting | Nothing is waiting on this person | "Waiting on {counterparty}" with the date it was last their turn | none |
| Not found | 404: a memo that is not theirs, a draft, or an id that does not exist | "This deal isn't available." One message for all three, so the page cannot reveal that a draft exists | "Go to your deals" |
| Too many requests | 429 | "Lots of requests right now. Try again in {Retry-After} seconds." | "Try again", disabled until the wait ends |
| Error | Network or 5xx | "We couldn't load this deal. Check your connection and try again." with the request ID if the body carries one | "Try again" |
| Action refused | 409 on an action, for example `due_date_has_passed` on accept | The API's own message, shown as given. For `due_date_has_passed`: "The agreed date has passed. Ask the brand for a new date." | "Ask for a change" |
| Stale | An action succeeds elsewhere; the pass is out of date | Re-read on focus and after every action. Show "Updated just now" | none |

A stage that is simply not reached yet is greyed text, not an error state.

## 8. Copy rules

- English only (D-054). All strings in `messages/en.json`; none in a component.
- Every status names **who** acted and **when**. A bare "Paid" is not shippable.
- Payment language states facts: "marked as paid", "confirmed received", "disputed". Never any word implying Colyv holds, moves, protects or releases money (CLAUDE.md section 2).
- Third person for the counterparty ("Waiting on Priya"), second person for the reader's own action ("Submit your work").
- No "verified", "trusted", "reliable", "guaranteed", "protected" anywhere on a pass.
- Buttons say what happens: "Accept memo", "Submit your work", "Approve work", "Ask for a revision", "Mark as paid", "Confirm I received it". Not "Submit", "OK".
- Money: `₹8,000`, Indian grouping, no decimals unless paise are real. Dates: `23 Sep 2026`. Both from the shared formatter.
- No emoji, no exclamation marks.

Next-action words, from the attention kinds the API returns (the API says "the words belong to the frontend"):

| `kind` | Who | Button |
|---|---|---|
| `answer_memo` | Creator | "Answer memo" |
| `deliver_work` | Creator | "Submit your work" |
| `resubmit_work` | Creator | "Resubmit your work" |
| `confirm_payment` | Creator | "Confirm I received it" |
| `payment_overdue` | Creator | None. It is a fact ("Payment is {n} days late"); the creator's actions are on the payment section |
| `respond_to_dispute` | Both | "Respond to dispute" |
| `draft_memo`, `revise_memo` | Brand | "Write memo", "Revise memo" |
| `review_proof` | Brand | "Review work" |
| `pay_creator` | Brand | "Mark as paid" after paying directly; the page says Colyv never handles the money |
| `review_applications` | Brand | Not a pass (it is before any memo); belongs to the brand's campaign screen |

## 9. Gaps in the API (backend requests, not design decisions)

None of these is built here. Each needs Adhi's decision.

| # | Gap | Why it matters | Smallest fix |
|---|---|---|---|
| B1 | **No stage, no rollup.** `GET /deal-memos/mine` returns memo status only. Proof and payment come from separate calls | The stack and any brand board cost many calls per screen (`ux.md` §7) | A `stage` and the next date on each item of `deal-memos/mine`, using the table in section 4 |
| B2 | A single read for one pass would save four calls on open | Same | Optional: proofs, payment state and dispute state included in `GET /deal-memos/{id}` |
| B3 | **Declined has no date.** `MemoRead` has `accepted_at`, `cancelled_at`, `sent_at`; nothing for declined | "Declined by {creator}" cannot say when. Every status must name when | A `declined_at` |
| B4 | **The change-request message is not returned.** `request-change` takes a 1,000-character message, but `MemoRead` carries only `revision_count`; the record holds typed text only as a fingerprint | The brand sees "Changes requested" without seeing what was asked. This is the core of that stage | Return the latest message on the memo, to the two parties only. Not verified whether notifications carry it |
| B5 | **Design-system vocabulary drift.** `StatusPill` includes `advance_paid` (the API has no advance), and `StageTracker` is a straight line with no branch | Pills would show states that cannot exist | Founder decision on the design system; no API change |
| B6 | **Who ended a deal early.** `withdrawn_early` covers both a brand cancel and a creator withdrawal before any work | The pass can say "Ended before any work was submitted" but not by whom. The record's `actor_role` may say; not verified | Either accept the wording or add the actor to the memo |
| B7 | **Deliverables are free text, and the first approval opens payment.** `approve_proof` calls `open_on_approval`, which creates the one payment record for the memo. A memo asking for three reels would owe the full fee after reel one. This contradicts rule 2 | Payment would open too early; "2 of 3" cannot be shown | A deliverable count (or a list of deliverables) on the memo; proofs belong to a deliverable; payment opens only when all are approved. Schema change and a change to payment logic: **needs an approved decision and a migration** (sensitive domain, CLAUDE.md section 5) |
| B8 | **No draft step.** A proof is only the live link; the memo must be `accepted`, and a second submission is refused while one waits | Rule 3 cannot be expressed | A kind on each submission (draft or live), the rule that live follows an approved draft, and new attention kinds for "review draft" and "submit draft" |
| B9 | **No campaign-level summary.** There is no endpoint that says how many deals on a campaign are finished | "Complete" (rule 4) and the brand's board both need it | A per-campaign summary of deals by stage, and a derived "Complete" flag (all deals finished). Not a stored status, so no migration for the flag itself |

## 10. Look

The pass is product UI, not identity artwork. The design system is explicit: **glass is the product, neo-brutalist is the identity, never mixed.** So:

- A pass uses the same surface as a `Card` (`surface-base`, `radius-card`, `elevation-raised`) but is built as its own element, because the perforation notches need `overflow: visible` and `Card` clips its edges. Not glass: it carries text under 24 px and money. If a glass layer is ever used, it is `glass-fill-strong`, never on glass.
- **No hard outline, no zero-blur offset shadow, no `brutal-*` token on the pass.** Those belong to marketing and identity surfaces.
- The boarding-pass idea is carried by structure, not ornament: a **perforation** is a dashed `line-hairline` rule with half-round notches at the card edges, separating the front from the back. It is decorative, so it uses only `line-hairline`, which is exempt from contrast because it carries no meaning.
- The strip uses `StageTracker`, which is linear, takes `stages` and `current`, and guides **at most five stages** (hence five, not six). At 360 px it does not fit five labels, so only the current label is visible (the others stay readable to a screen reader) and a line below reads "Stage 3 of 5: In progress". Branches (revision, dispute, ended) are a `StatusPill` beside it, not a new stage.
- Money: `MoneyCell`, tabular figures. References and seals: `code` style. Never in body copy.
- Icons: only the 13 the system has (`check`, `clock`, `alert`, `rupee`, `x`, `briefcase`, `user`, `bell`, and others). A concept with no icon uses a text label. No seal, lock or stamp glyph is invented. `StatusPill` supplies its own icon for the statuses it knows.
- Motion: stage change fades at `duration-base` with `ease-standard`. Nothing loops except the single skeleton pulse. Respect `prefers-reduced-motion`.
- On the marketing site a pass may be shown in identity style, as sample data labelled as such. That is a different artefact with different rules.

## 11. Accessibility and performance

- WCAG 2.2 AA (`docs/standards/frontend.md` §5, to be re-read before build).
- Stage is announced as text: "Stage 3 of 5: In progress, 2 of 3 approved. Waiting on {brand}." The strip is not colour or position alone.
- Every pill carries a word and an icon. Green and red are never the only signal.
- Tap targets 44 px; the focus ring is `state-focus`, never removed.
- The page never scrolls sideways at 360 px. The strip scrolls inside its own container.
- Money reads aloud as "8,000 rupees".
- Copy buttons (seal, reference) say what they copy and confirm with text, not only an icon.
- **Measured, not claimed:** no performance or accessibility figure is given here. They come from tools after a build exists.

## 12. Open questions for founders

1. **When does the pass appear?** Recommended: memo sent. Alternative: application accepted, with "Waiting for {brand} to send the memo". The API shows a creator nothing about a draft memo, so the alternative needs a pre-memo state the API does not model.
2. **Does `unconfirmed` count as Finished?** The brand has nothing left to do, but the creator has not answered. Recommended: keep it in "Needs you" for the creator while they can still confirm (the service accepts a late confirmation), and treat it as waiting for the brand.
3. **Shareable proof of a deal.** A third party cannot read the record today. If founders want one, it needs a decision on what is exposed and to whom.
4. **Several deliverables: answered, not yet built.** Founder rule: payment opens only when every deliverable is approved. Still open: (a) does a draft that nobody reviews approve itself after the window, as live work does (D-025), or wait for the brand? Recommended: approve itself after the same 7 days, recorded as `auto_approved`, because D-025's own reason is that a creator must not wait forever, and the live link is still the brand's to approve (`docs/PROPOSAL_DEAL_FLOW_RULES.md`, Decision 3a). This reverses my first suggestion, which was to wait; (b) if one of three deliverables is never delivered, what happens to the other two, and to the fee? The records give no rule; this needs the cancellation terms (D-026) read against partial delivery; (c) does a brand see the draft step as optional per memo, or always? The founder said always.
5. **Barter deals.** Recommended: Finished at approval, no payment section, and the delivery record counts them separately. Confirm the wording "Barter deal, no fee".
6. **Product name.** CLAUDE.md section 0 records the rename to Colyv as awaiting agreement; this spec avoids naming the product.

## 13. Checks before anyone builds this

- [ ] Five or more conversations with creators and brands about how they track a deal today, recorded in `docs/research/` (`ux.md` §2).
- [ ] A contract test confirms the live responses match sections 4 and 5, including that a declined memo carries no date until B3 is built.
- [ ] Requests B1 to B4 decided. B1, B3 and B4 block the stack and the "Changes requested" stage.
- [ ] Requests B7 to B9 decided and recorded as decision entries, each approved by the founder who owns the backend (Adhi, D-051), with a working downgrade for any migration. They block the "In progress" stage, the draft step and "Complete".
- [ ] Open questions 1, 2 and 4 answered.
- [ ] A usability test of the stage vocabulary with five people: can each say, from the strip alone, what is waiting on them?
