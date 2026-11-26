# Proposal: API requests from the frontend (R1 to R12)

**25 November 2026:** R7 to R12 added by the creator journey's build (D-200), each with the stopgap the website uses meanwhile. **R7 is the most urgent**: without it My applications cannot name most finished applications. **Checked 6 November 2026:** R1, R2, R3 and R6 are on `main` (their branches merged); R4 and R5 stand as below. The frontend item that waited on R6 (F304) is unblocked.

**Status, 4 November 2026:** R1 and R6 approved (Adhi: "do it yourself", D-153) and built on `feature/campaign-names`; R2 likewise (D-154), on `feature/applicant-summary`; R3 built as item 27 (D-140, D-144). R4 and R5 still open: R4 waits on the validation pack's consent wording, R5 on a decision for after launch, as this file recommends. **Originally:** Proposed. Written 28 October 2026 by the design and frontend side (Erode Harish's track, with Claude), for Adhi.

**What this is.** `frontend/design/screen-plan.md` plans every screen against the API on `main` at `0b2ea3d` (203 operations). Most of what the frontend first thought was missing is already built: the deal `stage` and `waiting_on`, the payments list and totals, deliverables as a list, account deletion, phone registration. Six things are still missing. They are listed in the order the frontend needs them. Each has a fallback, so none blocks the frontend; the fallbacks cost quality, and R1 costs the most.

**What it asks of Adhi.** For each request, approve it, change it, defer it, or say no. Order is yours. `CLAUDE.md` section 5 gates the database changes (R3, R4, R5) and R6 touches what clients may rely on. R1 and R2 add response fields only.

---

## R1. A brand's name on what a creator reads, and a campaign's title on the memo list

```
DECISION NEEDED: Brand name and campaign title where a person needs them
Context:      A creator browsing campaigns cannot see who the brand is: a campaign
              carries brand_id, brand_name_flag and verified_domain, but no name.
              The memo list (GET /deal-memos/mine) carries stage and waiting_on but no
              campaign title and no counterparty name, so a row in "My deals" cannot say
              which deal it is. Only attention items and the payments list carry names.
Update 28 Oct: the Deals screen is now built as a journey board (stages left to right, a
              dark card where it is the person's move) and every card wants the campaign and
              the other side's name. Today those come only from the payments list, so a deal
              with no payment yet (a memo sent, an agreement, work in progress) shows
              "Deal memo" and "Awaiting details". This is the most visible gap in the product.
Option A:     Add brand_name to CampaignRead (discover, for-me, mine, one campaign) and
              campaign_title plus counterparty_name to MemoWithStageRead. The frontend reads
              exactly these two names, `campaign_title` and `counterparty_name`, if present.
              | + a screen needs one call (ux.md section 7); no schema change, only joins
              | - a brand's name is now public on every open campaign (it already appears
                  on payments and attention)
              | effort S
Option B:     Leave as is. The frontend shows the verified domain and one extra call per row.
              | + nothing to build | - a creator cannot tell who is hiring them; N+1 calls
              | effort none
Recommended:  A, because the first question a creator asks about a campaign is "who?"
Risk & rollback: Response fields only; removing them is a one-line revert. Confirm the
              brand name may be shown to every signed-in creator.
Needed by:    About 10 November (creator screens are built 11 to 24 November).
→ Approve A, B, or modify?
```

## R2. A creator's summary on the applicants list, and applicant counts

```
DECISION NEEDED: Who applied, in one call
Context:      GET /campaigns/{id}/applications returns creator_id, pitch and quote, but
              no name, handle, city or niches. The brand's board needs them on every row.
              GET /campaigns lists campaigns with no applicant count.
Option A:     Embed a creator summary (display_name, handle, city, niches, and the
              one-line delivery record) in each application for the brand, and add
              applicant_count to the campaigns list.
              | + one call per screen | - a larger response | effort S
Option B:     No change. The frontend calls the media kit once per applicant and
              /campaigns/{id}/summary once per campaign.
              | + nothing to build | - 20 calls to draw one page; breaks the two-calls rule
Recommended:  A.
Risk & rollback: Response fields only. Creators must never see another creator's data
              through it: the embed is for the campaign's owner only, and the existing
              ownership test must cover it (CLAUDE.md section 8).
Needed by:    About 24 November.
→ Approve A, B, or modify?
```

## R3. Draft first, then the live link (item 27)

```
DECISION NEEDED: Does a creator send a draft before posting?
Context:      A founder rule of 4 October: the creator sends a draft, the brand approves
              it, then the creator posts and sends the live link. Today a proof is the
              live link only. This is item 27 in docs/BACKEND_COMPLETE.md, a product
              decision with a database change, and it affects the deal pass.
Option A:     Build it before launch.   | + matches the rule | - schema and clock change
                                         (D-025); effort M to L
Option B:     Launch with the live link only, add the draft step after launch.
              | + smaller launch | - brands approve work already posted
Recommended:  Adhi's call. The frontend is unblocked either way: the pass has five stages
              and the draft step appears inside "In progress" when it exists.
Schema request: Tables affected: proof. Migration: one. Rollback: downgrade drops the
              added column or value. Data impact: none on existing proofs.
Needed by:    A decision by 10 November if A; otherwise none.
→ Approve A, B, or modify?
```

## R4. The pilot join list (item 23)

```
DECISION NEEDED: Somewhere for the website's Join form to send
Context:      The homepage has a Join the pilot form with no endpoint (item 23). Consent
              wording belongs to the validation pack (CLAUDE.md constraint 6): not guessed.
Option A:     A public, rate-limited endpoint storing a phone or email and the consent
              text version shown. | + the form works | - a new table; DPDP wording needed
Option B:     No form at launch: people arrive from the app stores and invite codes.
Recommended:  B for launch unless the validation pack delivers the wording soon.
Schema request: Tables affected: one new table (waitlist). Migration: one. Rollback:
              drop it. Data impact: personal data; retention is the pack's question.
→ Approve A, B, or modify?
```

## R5. Proof per deliverable (item 26, "still owed")

```
DECISION NEEDED: One proof for each deliverable
Context:      Deliverables are a list (D-127) but a proof belongs to the memo. A memo
              with a reel and two stories cannot show which item a proof covers.
Option A:     Link each proof to a deliverable item. | + the pass tracks each one
              | - schema change; effort M
Option B:     One proof per memo, the note listing what it covers.
Recommended:  B for launch, A after it.
Schema request: Tables affected: proof. Migration: one. Rollback: drop the link.
→ Approve A, B, or modify?
```

## R6. Which features are switched off

```
DECISION NEEDED: A way for a client to know what is on
Context:      Several built features are off until an outside answer arrives: passkeys,
              connected accounts, the UPI pay link, Passport indexing, delivered push. A
              screen cannot hide what is not on if the API does not say. Today there is
              no features, config or capabilities route.
Option A:     GET /api/v1/features returning a small object of booleans, public or for
              any signed-in account, and a documented problem code for a switched-off
              route.   | + clients hide what is off, and switch on without a release
              | - one more contract to keep; effort S
Option B:     The frontend carries constants and flips them with each release.
              | + nothing to build | - a store release to turn on a feature
Recommended:  A. frontend.md already asks for feature flags (section 14).
Risk & rollback: A read-only route; removing it returns clients to constants.
Needed by:    About 10 November.
→ Approve A, B, or modify?
```

## R7. A campaign's title, brand and brand id on each of a creator's applications (most urgent)

```
DECISION NEEDED: Name the campaign on GET /api/v1/applications/me
Context:      My applications (C5, built 25 November 2026, D-200) lists a creator's
              applications. Each carries only campaign_id, so the screen reads each
              distinct campaign once: 1 + N calls, against ux.md's two-call rule.
              Worse, GET /campaigns/{id} answers 404 to a creator for any campaign
              that is no longer open (campaigns/service.py), and campaigns close after
              selection: most finished applications (accepted, not chosen) cannot be
              named at all, and their brand cannot be reported or blocked from there.
              And the reads share the campaign read's limit, 60 a minute an account:
              a creator with more than 60 campaigns sees "didn't load" on the rest.
Option A:     campaign_title, brand_name and brand_id on each item of /applications/me
              (and on one application), whatever the campaign's state, as R1 did for
              memos.   | + one call; every row named; report and block on every row
              | - three more fields to keep; effort S
Option B:     Keep the stopgap.   | + nothing to build | - finished applications
              show "This campaign isn't open any more" with no name
Recommended:  A.
Risk & rollback: Response fields only; clients ignore what they do not read.
Needed by:    Before the pilot. The stopgap is bounded (read once, kept 10 minutes,
              not re-read on focus, never retried) but cannot name a closed campaign.
→ Approve A, B, or modify?
```

## R8. Whether a handle is free, before the form is sent

```
DECISION NEEDED: A handle check for onboarding (C0)
Context:      A taken handle is found only when POST /creators/me answers 409
              handle_taken; the screen then takes the creator back to step 1. There is
              no route that says whether a handle is free (/creators/by-handle answers
              only published Passports).
Option A:     GET /api/v1/handles/{handle} answering { available: bool }, signed in,
              rate limited.   | + the field says "taken" as it is typed
              | - one more route, and it tells anyone signed in which handles exist
              (they are public on Passports anyway); effort S
Option B:     Keep the 409.   | + nothing to build | - a step back after Finish
Recommended:  B for the pilot; A if the usability sessions show people trip on it.
Risk & rollback: A read-only route.
→ Approve A, B, or modify?
```

## R9. "Your application" on a campaign a creator reads

```
DECISION NEEDED: The reader's own application on GET /api/v1/campaigns/{id}
Context:      The campaign screen (C3) shows Apply, or the application already sent.
              To know which, it reads the creator's whole application list, shared
              with Discover and usually cached; opened from a link, it is a third call.
Option A:     my_application { id, status, origin, created_at } on a campaign read
              by a creator, null otherwise; and the brand's payment record on the
              campaign too, so a campaign opened from a link is one call, not a chain
              of two (frontend.md section 4: in parallel, never in a chain; from
              Discover the website already starts from the card and asks in
              parallel).   | + one call always | - two fields; effort S
Option B:     Keep reading the list.   | + nothing to build | - a third call from a link
Recommended:  A, after R7.
Risk & rollback: A response field only.
→ Approve A, B, or modify?
```

## R10. A text's warnings before it is sent

```
DECISION NEEDED: Show the author the warning before sending (ux.md section 5, item 60)
Context:      ux.md says the author sees the same warning the reader will, before
              sending. The rules (money asked for, contact details) live in the backend;
              the website shows the pitch's warning only after it is sent, from the
              answer's text_flags. Writing the rules again in the client would let the
              two disagree.
Option A:     POST /api/v1/text-flags { field, text } answering the flags, rate
              limited.   | + one source of rules | - a call while typing (debounced);
              effort S
Option B:     Keep showing it after sending.   | + nothing to build | - the author
              learns after the brand can already read it
Recommended:  A.
Risk & rollback: A read-only check; removing it returns to after-sending.
→ Approve A, B, or modify?
```

## R11. Warnings on a deliverable's note

```
DECISION NEEDED: Flag deliverable_items[].note as the other free text is flagged
Context:      A campaign's deliverable notes are the brand's free text (up to 200
              characters), shown to creators, but text_flags covers only title,
              description and deliverables (campaigns/schemas.py). "WhatsApp 98765
              43210 to confirm" in a note gets no warning (trust-and-safety.md
              section 5).
Option A:     Add each note to text_flags, as field "deliverable_items.{i}.note".
              | + the screen shows it beside the note at once | - effort S
Option B:     Leave notes unflagged.   | - a gap in the warnings
Recommended:  A.
Risk & rollback: Response field values only.
→ Approve A, B, or modify?
```

## R12. Whether a campaign requires an ad disclosure

```
DECISION NEEDED: disclosure_required on a campaign
Context:      The screen plan (C3) shows a creator, before applying, whether the
              campaign requires an ad disclosure (ASCI). The memo carries it; the
              campaign read does not, so the campaign screen cannot say it.
Option A:     disclosure_required on CampaignRead (the brand's intent, confirmed on
              the memo).   | + terms before commitment | - effort S, and its wording
              is a legal.md question
Option B:     Show it from the memo only.   | - a creator learns it after applying
Recommended:  A, worded with the validation pack.
Risk & rollback: A response field only.
→ Approve A, B, or modify?
```

---

**Not requested, for the record:** brand logo, city and category (a brand's face is its name, verified domain and payment record); team seats (item 13) are not at launch; the admin console is a separate question in `frontend/design/execution-plan.md` section 6.
