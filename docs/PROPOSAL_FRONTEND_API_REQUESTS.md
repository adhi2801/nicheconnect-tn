# Proposal: six API requests from the frontend

**Status: Proposed.** Nothing here is built, approved or a decision. Written 28 October 2026 by the design and frontend side (Erode Harish's track, with Claude), for Adhi.

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

---

**Not requested, for the record:** brand logo, city and category (a brand's face is its name, verified domain and payment record); team seats (item 13) are not at launch; the admin console is a separate question in `frontend/design/execution-plan.md` section 6.
