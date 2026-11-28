# The dashboards (Today) and the campaign view, for creators and for brands

**Status: Proposed, 28 November 2026.** Nothing here is built. Harish's words are HD-007 and his message of 28 November (below); the look is D-203.

## What Harish asked for

"i need both the creator and brand to have dashboard. The brand should be able to view the collab status and the insights of the reel or post performing which is posted by the creator or posted in colab... and every information about the campaign and ongoing campaign should be able to be viewed by both creator and brands... use the reference i gave you now and the yellow one (frontend/prototypes/dashboard.html) and make a new one out of these... it shouldn't spoil the aesthetics of the website."

## 1. What is built, in this order, one page at a time with his yes (HD-006)

1. **Today, for a creator** and **Today, for a brand**: `/app`, one page that shows the one for the signed-in role.
2. **A campaign page, for both roles**: `/app/campaigns/{id}` (brand) and the same information read-only on `/app/discover/{id}` (creator, already built, extended with their own deal).

The look is the merge: the new reference's pill menu, white cards on the mint tint, lime, sage, big light figures; and the yellow prototype's content and structure (a dark "needs you" task card, a next-due ring, a row of progress bars, a figures row, a calendar, "campaign details" in sections). The prototype's butter yellow becomes lime; its cream becomes the tint.

### Creator's Today
Greeting and three figures (confirmed this month, on its way, open deals); **Needs you** (the dark card: up to five attention items with their one button); **Next due** (the ring with days left); **Coming up** (dates of deals); **Your applications** (status of each); **How brands pay** (each brand's payment record, shown only where the backend has one); **Your numbers** (what the screenshots you sent said, per post, with "read from your screenshot"). A design slot holds the large card the reference uses a photograph for.

### Brand's Today
Greeting and figures (creators applied, deals open, to mark as paid); the progress row (applications reviewed, memos agreed, work approved, paid and confirmed: from the campaign summary); **Needs you** (dark card); **Campaigns at a glance** (each ongoing campaign with its stage counts); **Collaborations** (each deal: creator, stage, whose move it is, due date); **Performance** (the numbers the creators' screenshots showed, per post and per campaign); **Payments** (to mark as paid, with totals).

### Campaign page (both roles)
Everything about the campaign: pay, deliverables, description, cities, niches, closing date, status; for a brand also applicants by status, deals by stage and the per-deal results; for a creator, their own application or deal and the brand's payment record. Both see the same facts about the campaign itself.

## 2. The data limit, stated plainly (decision needed)

**The backend has no live post performance.** Instagram and YouTube connections are built but **switched off** until Meta's App Review and Google's verification (BACKEND_COMPLETE.md). What exists is the numbers **read from the creator's proof screenshot** (views, reach, impressions, likes, comments, saves, shares), per file on each approved deal and summed per campaign (`GET /campaigns/{id}/report`), labelled by the contract and D-070 as **"Read from screenshots, never verified"**: a screenshot can be edited, and a creator can mark a reading wrong (those are left out). So:

- Performance is shown **per post and per campaign totals, not as a daily graph** (there is no time series; the prototype's "Reach, last 7 days" cannot be built from this data and will not be faked).
- Every figure says where it came from. A figure shown in abbreviated form on the screenshot (12.5K) is marked as not exact. `null` is never shown as zero.
- When Instagram is connected for real, the same cards switch to verified numbers; nothing else changes (one place in `src/lib`).

## 3. API each page reads (all exist; nothing new is asked of Adhi)

`GET /me/attention`, `GET /campaigns`, `GET /campaigns/{id}/summary`, `GET /campaigns/{id}/report`, `GET /deal-memos/mine`, `GET /payments/mine`, `GET /payments/mine/totals`, `GET /applications/me`, `GET /brands/{id}/reliability`, `GET /creators/{id}/delivery-record`, `GET /deal-memos/{id}/proof` and its files' readings. Brand names and campaign titles are on every memo (R1, D-153).

Gaps, filed as requests rather than worked around: a creator's own results summed over all their deals in one call (today one call per proof); the campaign id on a memo row if it is not carried; a brand's list of all open deals with creator names (R2 gives applicants only).

## 4. The twelve dimensions

- **Quality:** each state of each page screenshotted and checked (loading, empty, error, partly done, all clear); the existing accessibility checks (WCAG 2.2 AA, 7:1) in light and dark at both widths for both roles; unit tests for every rule (what counts as "needs you", the progress shares, the performance sums, `null` never zero); the rules broken on purpose; an independent review before merge.
- **Novelty:** not yet researched: the strongest competitor's campaign-performance view will be looked up, dated and set beside ours when the page is shown, and no claim about it is made until then. What is ours by design: a number always says where it came from; a creator sees a brand's payment record and a brand sees a creator's delivery record; the whole deal sits on one sealed record. Its limit today: numbers come from screenshots.
- **Architecture:** frontend only: `src/components/today/`, a new `src/components/dashboard/` for shared parts (figure, ring, split bar, dotted bars), pages under `src/app/app/`. No backend change.
- **Research:** the references are the COREHR dashboard (Dribbble, Harish's image) and our own prototype; the benchmark for each card is named when the page is shown.
- **Security:** a creator never sees another creator's numbers or a brand's private data; a brand sees only deals and proof on its own campaigns. Both are enforced by the backend; the client only shows what comes back.
- **Privacy and law:** performance numbers are creators' own screenshots' contents; never labelled "verified" (D-070, `legal.md` section 1 rule 3). No personal data beyond what the API already sends the party. People appear as names and initials, never photographs (D-142).
- **Trust and safety:** report and block stay one tap from anything another party sent (D-201). A creator can mark a reading wrong; a brand sees those counted apart.
- **Performance:** each page makes its calls in parallel (never a chain), within the budgets; the signed-in JavaScript (about 215 KB compressed against 150 KB) is measured again and reported; charts are drawn with CSS and SVG, no chart library.
- **Design:** this document and the screenshots shown before each page is built on.
- **Business:** brands see what their campaign achieved and what is left to do on one page; creators see what needs them and what they are owed. Cost: the performance numbers rely on creators sending screenshots.
- **Reliability:** every card has its own loading, empty and error state, so one failed call does not blank the page; retries follow the standard (busy is retried, 429 never).
- **Maintainability:** one `Figure`, `Ring`, `SplitBar`, `DotBars` and `Card` used by both roles; all words in the message catalogue; rules in `src/lib/` with tests.

## 5. Gates, risks, undo

- **Gates:** scope (adds the campaign page and performance cards to the approved plan); no dependency, database, CI or backend change.
- **Risks:** the screenshot-only performance data is thin and will look sparse until creators send proofs; seeded data in the local backend has few readings, so screenshots of this page use the stand-in's sample data and say so.
- **Undo:** its own branch work on `feature/website-structure`; nothing merges without Harish's approval of each page.
