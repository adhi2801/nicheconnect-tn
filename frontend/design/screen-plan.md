# Colyv screen plan

**Status: Proposed.** Written 28 October 2026 for Erode Harish. Nothing here is approved or built. Deadline for the build to be ready for testing: **10 December 2026**.

## 1. How to read this

This plan decides, for every screen, what the person needs to know, in what order, and what the one thing is that they can do. It is built from three inputs:

1. **What the API really returns** (`docs/api/openapi.json`, 65 endpoints). A field the API does not return is marked **GAP** and listed in section 8. A screen that needs a missing field is a backend request, not a frontend decision.
2. **The binding standards**: `docs/standards/ux.md` (one primary action per screen, four states, 360 px up) and `docs/standards/frontend.md`.
3. **The design already agreed**: five-stage deal pass, Passport with two separate consents, one theme (black and butter yellow on warm cream, `tokens/tokens.json`).

The psychology notes are design reasoning from widely used principles. They are **not measured results for Colyv's users**. Each becomes a hypothesis that the usability tests in `ux.md` section 2 confirm or reject.

## 2. The two people

**Creator** (a Tamil Nadu creator, on an Android phone, on mobile data, with a few minutes at a time).

| Moment | What they feel | What the screen must do |
|---|---|---|
| Opening the app | "Is anything waiting on me? Did someone pay?" | Answer in one glance, before anything else |
| Browsing campaigns | "Is this worth my time? Will they actually pay?" | Show pay, dates and rights up front, and the brand's real payment record |
| After applying | "Did they see it? Why no reply?" | Show a dated status and, after a no, the reason |
| Doing the work | "What exactly did I agree to?" | Keep the agreed terms one tap away |
| Waiting for payment | Anxiety, sometimes anger | Show exact facts: who marked what, and when. Never imply Colyv holds money |
| A dispute | Fear of being ignored | A calm timeline where both sides add evidence |

**Brand owner** (a small business owner, laptop or phone, not a marketing professional, short of time).

| Moment | What they feel | What the screen must do |
|---|---|---|
| Opening the dashboard | "What needs me today?" | One ranked list of actions |
| Posting a campaign | "Will I get it wrong?" | Four short steps, sensible defaults, a review before publishing |
| Choosing creators | "Who is real? Who delivers?" | Show the delivery record and the pitch side by side, with no invented scores |
| Writing the memo | "Am I covered?" | Plain fields: fee, due date, rights, disclosure |
| Paying | "Did I do this right? Is it on record?" | A short sheet: method, reference, done. Mark several at once |
| Closing out | Wanting proof it was done properly | The sealed deal record |

## 3. Rules every screen obeys

1. **One screen, one job, one primary action** (Hick's law: fewer choices, faster decisions). Secondary actions are quiet. A destructive action is never in the primary position.
2. **Answer "what do I do now?" before "what is happening?"** People open a work app with a question. Today is the attention list, not a dashboard of numbers.
3. **Every status has a who and a when.** "Chennai Bakes marked this paid on 6 Oct, 12:30." Never a bare "Paid". This is the ux.md honest-status rule, and it is what builds trust.
4. **Terms before commitment.** The creator sees pay, dates and rights before applying, and the full memo before accepting. This reduces regret and later disputes.
5. **Progress is visible and finite** (goal-gradient: effort feels lighter when the end is in sight). The deal is five stages. No form has more than four steps. Onboarding is two steps.
6. **Cut effort with defaults.** The quote starts from rate guidance (range, number of creators counted, "guidance, not a quote"). Typed text survives a failed send.
7. **Proof comes from records, never invented.** Delivery record and payment record only. A new person shows "no history yet" as a neutral state, never as a penalty. No fake counts, logos or testimonials anywhere.
8. **Money screens are calm and factual.** No countdown pressure, no red unless something is truly overdue, no celebration on a payment being marked. The one earned moment is a finished deal and its record (peak-end: people remember the end).
9. **Familiar patterns** (Jakob's law): phone-code sign-in like UPI apps, list then detail, bottom tabs on the phone, a payment sheet that mirrors how people already pay.
10. **Reach and reading.** On the phone the primary action sits in thumb reach at the bottom. Targets are at least 44 px. Text scales to 200%. On the web, reading width stays near 65 characters.
11. **Ask for sensitive things only when needed, and say why at that moment.** Phone number at sign-in. Publishing the Passport and showing prices are two separate choices.
12. **Empty states teach the next step. Error states give the fix.** No blame, no jargon. Every screen has loading, empty, error and success.
13. **Respect time.** Today shows the top five items and a "see all". The API says when the list is truncated.

## 4. Structure

One plan, two surfaces: the **app** (Flutter, phone) and the **website** (Next.js, laptop). The role from sign-in decides which screens a person sees. The same screen spec drives both; the phone gets a single column and the website gets a side panel.

**Creator tabs:** Today · Discover · Deals · Inbox · Me
**Brand tabs:** Today · Campaigns · Deals · Inbox · Me

Why five: it is the most a thumb-reach bar holds without crowding, and it matches the wireframes. Passport, rate card, channels and earnings live under **Me** for creators, because they are set up once and visited rarely. Paying lives inside **Deals** for brands, with a shortcut from Today.

**Depth rule:** any task is at most three taps from Today.

## 5. Scope for 10 December

**Must** (the six journeys in `ux.md` section 3, plus what they need to work):
sign-in, onboarding, Today, Discover, campaign, apply, my applications, deals, deal pass, memo, send work, review work, pay, confirm payment, dispute, deal record, inbox, Passport, account, brand campaign creation and applicants.

**Should** (if time allows): suggested creators (matches), rate guidance on the apply screen, homepage restyled to the one theme, public Passport page polish.

**Not before 10 December:** Instagram metrics, the Copilot assistant, saved campaigns, an earnings summary (no API), command palette, anything marked GAP that the backend does not deliver in time.

## 6. Screen specs

Format: **Job** (the one feature) · **Asks** (the question in the person's head) · **Shows** in priority order, with the API field · **Action** (the one primary) · **Not here** · **States** · **Why** (psychology) · **Gaps**.

### Shared

**S1. Sign in**
- Job: get a login code.
- Asks: "Is this safe? What do you want my number for?"
- Shows: choice "I'm a creator / I'm a brand" (the role is sent with the code check); phone field; one line why the number is needed. `POST /auth/otp/request`.
- Action: **Send code**.
- Not here: marketing, social login, password.
- States: wrong number format (fix hint); too many tries (rate limit, say when to retry).
- Why: familiar phone-code pattern; the reason for asking sits next to the question.

**S2. Enter code**
- Job: prove it is you.
- Shows: where the code was sent (last digits), code boxes, resend timer, change number. `POST /auth/otp/verify` returns `is_new` and `role`.
- Action: **Confirm** (sends on the last digit).
- States: wrong code, expired code, account already has the other role (409): "This number is a brand account. Sign in as a brand." Code length is unconfirmed, drawn as six.
- Why: the account state decides the next screen: new goes to onboarding, existing goes to Today.

### Creator

**C0. Onboarding, 2 steps** (target: first application in under 5 minutes, per ux.md)
- Step 1 "About you": display name, handle (live check that it is free, shown as the public address). Action: **Continue**.
- Step 2 "Where and what": city, niches (pick up to a few), languages. Action: **Finish**. `POST /creators/me`.
- Not here: bio, channels, prices. They come later, with a quiet nudge on Today.
- Why: two short steps with a visible "1 of 2" are completed more often than one long form (goal-gradient). Everything else waits until it is useful.

**C1. Today**
- Job: tell me what needs me now.
- Asks: "What should I do first?"
- Shows (P1): up to five items from `GET /me/attention`, most urgent first. Each item has a verb ("Confirm you received it", "Answer the memo", "Resubmit your work", "Send your work"), the brand (`counterparty`), the campaign (`campaign_title`), the amount (`amount_paise`) and the date or days left (`due_on`, `days_left`). (P2) a quiet "all clear, next date is 18 Oct" line when empty. (P3) one nudge at most: publish your Passport (`passport_published_at` empty) or a hint from `GET /applications/me/feedback`.
- Action: the top item's button. Every item has its own button; the top one is visually primary.
- Not here: income charts, discover feed, statistics.
- States: loading skeleton; empty "Nothing needs you. Browse open campaigns" with a button to Discover; error with retry; truncated shows "See all".
- Why: relieves uncertainty first; one clear next step lowers the effort to act (Fogg: motivation plus ability plus a prompt).
- Gap: a "waiting on others" group needs the memo list to carry campaign title and brand name (G3).

**C2. Discover**
- Job: find a campaign worth applying to.
- Asks: "Is this worth my time?"
- Shows per card: campaign title, brand, pay (`budget_min_paise` to `budget_max_paise` or "Barter"/"Commission"), type (`campaign_type`), cities, closing date (`applications_close_on`), the brand's payment record in one line when it exists (`/brands/{id}/reliability`). Filters: city, niche, type, minimum budget (`GET /campaigns/discover` supports exactly these).
- Action: tap a card to open it (no buttons on cards).
- States: empty "No open campaigns match. Clear a filter" with the filter chips named; loading skeleton cards; error retry; infinite list by cursor.
- Why: pay shown as a range on the card respects the person's time; the brand's real record is the only trust signal, and is absent for new brands rather than faked.
- Gaps: brand name and payment record are not on the list item, so the card needs one extra call per brand (G1).

**C3. Campaign**
- Job: decide whether to apply.
- Shows: title, brand and its payment record, pay range, what to deliver (`deliverables`), description, cities, niches, closing date, whether disclosure is required. Your earlier application if any.
- Action: **Apply**. If already applied: shows the application status instead.
- Why: everything needed to decide is on one page, above the action. Terms before commitment.

**C4. Apply**
- Job: send my application.
- Shows: a quote field starting from rate guidance (`GET /rate-guidance`: median, the middle range, how many creators were counted, "guidance, not a quote"); a pitch field (short, with a counter); the campaign budget as a reminder. `POST /campaigns/{id}/applications`.
- Action: **Send application**.
- States: quote far above budget gets a gentle note, not a block; failed send keeps the text.
- Why: an honest anchor reduces blank-field stress; seeing the budget avoids a rejection nobody wanted.

**C5. My applications**
- Job: see where each application stands.
- Shows: list grouped by status (`submitted`, `shortlisted`, `accepted`, `rejected`, `withdrawn`), each with the date it last changed (`status_changed_at`). A rejected one shows the reason (`rejection_reason`, `rejection_note`). A short insight at the top from `GET /applications/me/feedback` ("most rejections were about budget") only when there are enough applications.
- Action: tap one for detail; **Withdraw** lives inside the detail.
- Why: dated status plus a reason turns silence into information, which is the creator's biggest frustration.

**C6. Deals**
- Job: see all my deals and which need me.
- Shows: three groups: Needs you, Waiting on others, Finished. Each row is a pass strip: brand, campaign, fee, five-stage bar, one-line status. `GET /deal-memos/mine`.
- Action: tap a row to open its pass.
- Gap: rows need brand name, campaign title and the derived stage (G3).

**C7. Deal pass (the hub of one deal)**
- Job: show where this deal is and what to do next.
- Shows (front): five stages (Memo sent, Agreed, In progress, Payment, Finished) with the current one marked; the single next action; fee and due date. Branches (changes requested, dispute, declined, cancelled) are pills, not stages. Stage is derived, never stored.
- Shows (back, one tap): the agreed terms, the work list, payment, dispute if any, the deal record link.
- Action: the one next action for the current stage (answer memo, send work, confirm payment).
- Why: one object per deal, one next step; the finite bar makes progress visible.
- Gap: the stage is not an API field today (G3).

**C8. Memo (read and answer)**
- Job: understand the terms and answer.
- Shows: fee, content due date, what to deliver, usage rights days, payment due days, approval window, cancellation fee, disclosure required, extra terms, who sent it and when. `GET /deal-memos/{id}`.
- Action: **Accept memo**. Quiet: **Ask for a change**, **Decline** (each opens a short reason sheet).
- Why: all terms on one screen, in plain labels, before the person commits.

**C9. Send work**
- Job: submit a post for approval.
- Shows: format, link to the content, note, a disclosure checkbox when required (`disclosure_confirmed`), the brand's last revision note if any. `POST /deal-memos/{id}/proof`.
- Action: **Send for approval**.
- Gap: the agreed flow is draft first, then the live link; today the API has the live link only (G5).

**C10. Payment (creator)**
- Job: confirm money arrived, or say it did not.
- Shows: amount, due date, state (`due`, `late`, `unpaid`, `paid`, `unconfirmed`, `confirmed`), when and how the brand marked it (`marked_paid_at`, `method`, `reference`).
- Action: **I received it**. Quiet: **I have not received it** (opens dispute).
- Not here: any wording that suggests Colyv holds or moves money.

**C11. Dispute (both roles)**
- Job: put my side on the record.
- Shows: state, who opened it, response due date, a timeline of entries (opened, response, evidence, closed) with who and when, evidence links. `GET/POST /deal-memos/{id}/payment/dispute`, `.../entries`, `.../close`.
- Action: **Add to the record**. Closing it records how it ended; nobody here decides who is right.
- Why: a neutral, dated timeline reassures both sides that nothing can be quietly changed.

**C12. Deal record (both roles)**
- Job: show proof that this deal's history is intact.
- Shows: "The record holds together" (`intact`), terms unchanged since accepted, a readable list of entries (what, who, when), the latest seal, and the checkpoint proof. `GET /deal-memos/{id}/record`, `.../record/proof`.
- Action: **Check this record** (the proof lookup).
- Why: the finished-deal moment. A person leaves with something they can show.

**C13. Inbox (both roles)**
- Job: read what happened.
- Shows: notifications newest first, unread marked, each links to the right deal or application. `GET /notifications`.
- Action: tap an item; **Mark all read**.

**C14. Me (menu)**
- Shows: Passport (published or not), Rate card, Channels, About you, Account.

**C15. Passport**
- Job: control what the public sees.
- Shows: a live preview of the public page; two separate switches: publish, and show prices. The public address. `POST /creators/me/passport/(un)publish`, `rate-card/(un)publish`.
- Action: **Publish my Passport** (or **Take it down**). Taking down can take up to 5 minutes to reach everyone, and the page says so.
- Why: two consents, kept apart, so showing prices is never a side effect.

**C16. About you** (name, handle, city, niches, languages, bio, with a counter) · **C17. Channels** (Instagram, YouTube: link, followers and average views, marked as self-reported, with the date) · **C18. Rate card** (packages: title, format, platform, price, delivery days, usage days; rate guidance beside each) · **C19. Account** (sign out, sign out of all devices, download my data; account deletion is a GAP, G9).

### Brand

**B0. Brand setup**: name and email, one screen. `POST /brands/me`. (The profile is only name and email today, G1.)

**B1. Today**: same structure as C1. Verbs: "Review 3 new applications", "Write a memo for Karthik Bites", "Approve Priya's draft", "Mark Suresh Snaps as paid", "Payment is 2 days late". One primary action, the top item.

**B2. Campaigns**: list with status (`draft`, `open`, `closed`, `cancelled`), applicant count, closing date. Action: **New campaign**. Gap: no applicant count on the list (G2).

**B3. New campaign, 4 steps** (one job each, "step n of 4"): (1) What: title, description, niches, cities. (2) Budget: type (paid, barter, commission, local business) and range. (3) Deliverables and closing date. (4) Review: everything in plain words, then **Publish**. A draft saves at each step. `POST /campaigns`, `PATCH`, `.../publish`.

**B4. Campaign (applicants)**: applicants grouped by status; each row shows name, city, niches, quote, pitch's first line, and the creator's delivery record in one line. Action: tap one. Gap: the list has only `creator_id` (G2).

**B5. Creator (applicant profile)**: media kit (bio, channels, packages, languages, member since), delivery record (completed, delivered, delivered on time share, disclosure confirmed share, overdue now), pitch and quote. Actions: **Shortlist** as the primary; **Accept**, **Reject** (with a reason from the list) as quieter. `GET /creators/{id}/media-kit`, `.../delivery-record`.

**B6. Suggested creators** (Should): the matches list with the reasons shown plainly ("Food, Madurai, 3 accepted deals"). Action: **Invite**, if the backend gets it; otherwise view only.

**B7. Write memo**: fee, content due date, deliverables, usage rights, payment due days, approval window, cancellation fee, disclosure, extra terms. Defaults filled. Action: **Review memo**. **B8. Review and send**: the memo exactly as the creator will see it; **Send memo**.

**B9. Deals**: same grouping as C6. **B10. Deal pass**: same as C7 from the brand's side.

**B11. Review work**: the submitted content, format, disclosure checkbox state, creator's note. Actions: **Approve** (primary), **Ask for changes** (needs a note). The approval window and auto-approval date are shown.

**B12. Pay creators**: the list of payments due, a selection, then one sheet: method (UPI, bank transfer, cash) and reference. **Mark as sent**. Colyv does not move the money; the sheet says "You pay the creator directly." `POST /brands/me/payments/mark-paid`, `.../payment/mark-paid`. Gap: no list of all payments due (G6).

**B13 to B15**: dispute, deal record, inbox as C11 to C13. **B16. Me**: brand profile, how my payments are seen (`/brands/{id}/reliability`), account.

### Website only

**W1. Homepage**: the existing homepage, restyled to the one theme (Should). **W2. Public Passport** (`/c/handle`): `GET /creators/by-handle/{handle}`; sign-in to work with the creator is the one action; a not-found state when unpublished. **W3. Join the pilot**: a form with no endpoint behind it (G8).

## 7. Cross-screen patterns

- **Status pill:** always a word plus an icon, never colour alone. Words come from the API values, in plain English.
- **Money:** whole paise on the wire, `₹1,50,000` on screen.
- **Dates:** `17 Sep 2026`; relative only for "2 days left".
- **Four states** on every screen, designed once as components.
- **One bottom action bar** on the phone, one top-right action on the web.

## 8. Gaps found in the API (backend requests for Adhi)

| # | Gap | Screens hit |
|---|---|---|
| G1 | No brand name, logo, city or category: `brand_id` only on campaigns, applications and memos; brand profile is name and email | C2, C3, C5, C6, B16 |
| G2 | Applications list has `creator_id` only: no name, handle, city or niches; campaigns list has no applicant count | B2, B4 |
| G3 | Deal memo list has no campaign title, no counterparty name, no derived stage | C6, C7, B9, B10 |
| G4 | Deliverables is one free-text field; the pass needs several | C7, C9, B11 |
| G5 | No draft-then-live-link step (rules B7 to B9 in the deal-flow proposal, not approved) | C9, B11 |
| G6 | No list of payments, no earnings or dues summary: one read per deal would be a call per row | B12, Me, Earnings |
| G7 | No Instagram metrics endpoints; the Meta approach has no proposal yet | Passport, B5 |
| G8 | No pilot waitlist endpoint | W3 |
| G9 | No account deletion. Export exists. Retention and deletion rules need the compliance pack, not a guess | C19 |
| G10 | No device-token endpoint for phone notifications | C13 |

## 9. Conflicts to settle

- `docs/standards/frontend.md` still says Tamil and English, and lists React Native as undecided. Tamil was dropped (D-054) and the stack is Flutter and Next.js.
- This frontend sits in the backend repository, which `CLAUDE.md` forbids until Adhi approves and writes a decision entry (PR #78).
- `ux.md` section 2 asks for 5 or more user conversations before designing a flow and a test with 5 users before building it. A 10 December finish with testing afterward skips that order. Recommended: test the clickable prototype with 5 creators and 5 brands in the second and third week, in parallel with the build.

## 10. Plan to 10 December

43 days from 28 October.

| Dates | Work | Done when |
|---|---|---|
| 28 Oct to 3 Nov | Approve this plan and scope. Design system v1 in code: tokens, type, about twenty core components in Flutter and on the web. Install Xcode and the Android SDK. | Components exist with all states; plan signed off |
| 4 to 17 Nov | Creator journey, designed and built screen by screen: S1, S2, C0 to C13. | A creator can sign in, apply, and follow a deal to the record, on sample data |
| 18 Nov to 1 Dec | Brand journey: B0 to B15. Public Passport page. Homepage restyle if time allows. | A brand can post a campaign, choose a creator, send a memo, mark paid |
| 2 to 8 Dec | Connect everything to the real backend. All four states on every screen. Accessibility pass. Polish. | The six core journeys run end to end |
| 9 to 10 Dec | Freeze, fix list, handover for testing. | Testing can start |

**What this depends on:** scope held to the Must list; G1 to G3 answered by about 14 November, or the screens use a stated fallback; Adhi approving the repository move; each design decision answered within two days. Design and build happen in the same pass per screen, in real code, so no throwaway mock-ups are drawn.

**Risk, plainly:** this is tight for two apps and a website. The first item to drop is the Should list, then the website's polish, never the four states or accessibility.
