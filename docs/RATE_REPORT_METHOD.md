# How the quarterly city rate report is made (method version 1)

**For:** anyone reading, quoting or checking a NicheConnect TN quarterly city rate report: creators pricing work, brands budgeting, journalists, and anyone who wants to know exactly what a figure means. **Method version 1**, in force from 20 November 2026 (item 84, D-200). Every report says which version made it (`method_version`); a change to anything below is a new version, and a report already published never changes.

This page is the plain-English twin of the code: `app/modules/insights/rate_report_rules.py` (the floors and the rounding), `app/modules/insights/rate_report_figures.py` (which facts are counted) and `app/modules/insights/asking_prices.py` (which asking prices count, shared with city figures and fair-rate guidance).

---

## 1. What a report covers

- **One closed quarter** of the Tamil Nadu calendar, written `YYYY-Qn`: Q1 is 1 January to 31 March, Q2 April to June, Q3 July to September, Q4 October to December. A quarter runs from midnight at its start in Tamil Nadu to midnight at its end.
- **Built once**, on the first morning (06:00 Tamil Nadu time) after the quarter ends, and never built again by the job (a withdrawn quarter is corrected only by an admin, below). `built_at` is the moment it was really built, and `as_of` that day. Every morning's run then checks, once: a closed quarter with no report **three days** after it closed (however long ago), or a built report still unpublished after **14 days**, is logged as an error for us to act on. A quarter whose report was missed is never built late, since its asking prices cannot be worked out again.
- **Published by a person.** A report starts unpublished; an admin reads it, figures and all (`GET /api/v1/admin/rate-reports/{quarter}`, each read written to the admin log), and publishes it. From then on the database refuses any change to it. If a report is found wrong, it is **withdrawn**, with the reason shown to everyone who asks for it, and never quietly edited.
- **Corrected under a newer method** (D-201). Once the method has a newer version, a withdrawn quarter can be built again under it by an admin (`POST /api/v1/admin/rate-reports/{quarter}/rebuild`, written to the admin log): a new report for the same quarter that names the withdrawn one it replaces. It is read and published like any other, and readers then get it; the withdrawn report stays as it was, in the archive with its reason. Its asking prices are the rate cards on the day it was rebuilt, as its `built_at` and `as_of` say, since a past quarter's cards are not kept. The database refuses any other second report for a quarter.

## 2. What creators ask (asking prices)

- **Only published rate cards**, by creators who chose to show their prices to anyone; only active accounts (a suspended account's prices never count); rupees only.
- **By city, platform and format**, for every city with at least five creators who published their Passport. A city is matched however people spell its capitals or spaces, and shown as most of its creators spell it.
- **Statewide by audience band**: the creator's own channel on that platform decides the band (under 10k, 10k to 50k, 50k to 100k, 100k to 500k, 500k and over). Follower counts are what creators stated, with the date they stated them; we did not check them. `audience_figures_from` is the oldest such date behind a band.
- **Each creator counts once.** A creator's packages for one platform and format are reduced to their own median first, so one creator with five Reel packages counts as one voice.
- **A cell shows its lower quarter, median and upper quarter only when at least 5 creators are behind it.** Never a minimum or a maximum: each of those is one person's price.

Asking prices are the published rate cards **on the day the report was built**. Rate cards are edited in place, with no history, so a past quarter's asking prices cannot be worked out again later; that is why the report is a stored snapshot.

## 3. What was agreed (agreed fees)

**Switched off today** (`RATE_REPORT_AGREED_FEES`, D-200 Decision 1). Every report built while it is off says `agreed_fees_included: false`, and every city's `agreed_fees` is null. It stays off until a lawyer answers the questions in section 6 and a founder amends D-078, which says no public figure is built from a deal. Switching it on changes no report already built.

When it is on:

- **Which deals count:** a deal memo accepted inside the quarter and still accepted when the report is built (never cancelled), in rupees, with **exactly one deliverable, of quantity 1**, so its fee is for one piece of work on one platform in one format. Both sides' accounts must be active. The city is the creator's.
- **Barter deals** (goods, not money) count towards the cell's number of deals and are shown as a share (`barter_share_percent`), never as a price.
- **A cell is shown only when:** at least **5 deals**, from at least **5 different creators** and **3 different brands**, with **no single brand behind more than half** of them. Below that, every figure in the cell is null.
- **The fee figures** need the same of the paid deals alone, and more (amended 22 November 2026, D-201, before any report included agreed fees):
  - **at least 10 paid creators**: below that a cell shows its counts and barter share but no fee at all; from 10, the median and both quarters together, never the median alone;
  - **the p% rule, p = 10, against two who collude**, applied twice: to the paid fees summed per creator, and summed per brand. A cell's fees are shown only when what is left after taking away its **three largest** contributors comes to at least **10% of the largest**. Then no two contributors together, knowing their own fees, can estimate the largest's to within 10% from the cell's total; and so neither can the second-largest alone (the plain rule, two largest taken away). One consequence, by design: a cell whose paid deals come from only three brands never shows a fee, since any two of them know all but the third's.
- Each creator's own median fee comes first, so one creator with many deals counts once.

## 4. Why these floors (Decision 2, option A)

- **Five creators** is the floor city figures and fair-rate guidance already use (D-056, D-078), so the three never disagree about what is enough to say.
- **Counts of one or two people are disclosive**, and hiding small cells does not stop someone working a figure out by subtracting one table from another (UK Government Statistical Service, "Statistical disclosure control for tables produced from administrative data", 19 August 2026). The quarterly freeze helps here: a figure that changes live lets someone watch one price move; a frozen one does not.
- **The three-brand and no-brand-over-half rules count deals, not money.** They are a frequency floor, not the value-based "dominance" rules statistics offices apply to tables of money; until 22 November this page said they followed those rules, which was not so (the independent review of item 84). A brand behind half the deals can still be behind nearly all the money.
- **The p% rule** is that value-based rule, as defined in the *Handbook on Statistical Disclosure Control*, 2nd edition, chapter 4 "Magnitude tabular data", table 4.2 and its note on coalitions (read at sdctools.github.io/HandbookSDC on 22 November 2026): a cell is unsafe when its total less its two largest contributions is under p% of the largest, and, for a coalition of n − 1 respondents, its total less its n largest. We apply the coalition form for two (the three largest taken away) with p = 10, to creators and to brands. **Residual, stated:** three or more who collude, or one person behind several accounts or brands, can still narrow a fee down; the count floors and the 10-creator floor make that costlier, not impossible. And the rule protects a total; we publish a median and quarters of per-creator medians, which give away less than a total, rounded to ₹100.
- **Any fixed floor can be met with fake accounts** (Kenthapadi and Tran, PriPeARL, CIKM 2018: "the attacker can create k−1 or more fake accounts"). For asking prices the harm is small, since a published rate card is already public. For agreed fees the attack needs three brands and five accepted deals, under the dominance rule.
- **We add no noise.** Our figures are facts from the record (`docs/standards/legal.md` section 1, rule 4); a noisy figure would not be.

## 5. Rounding, nulls and the fingerprint

- **Every figure is rounded to the nearest ₹100** (half up), in paise in the data (`10000` paise is ₹100), so a published figure is not one person's exact price.
- **Null means "not enough to say"**, never zero. A screen must draw it as "not enough to say".
- **`body_sha256`** is the SHA-256 of the report's `body` written as canonical JSON: keys sorted, no spaces, plain ASCII, with JSON's own `\uXXXX` escape for any other letter (Python's `json.dumps(body, sort_keys=True, separators=(",", ":"))`). Anyone holding a copy can recompute it and compare.

## 6. Open questions (constraint 6: asked, never guessed)

These wait on the lawyer, through the validation pack (`docs/standards/legal.md` section 3.1):

1. Whether an aggregate held to these floors is personal data under the DPDP Act.
2. Whether counting agreed fees, even anonymously, needs a notice, consent or a term in the deal memo.
3. Whether a creator who later unpublishes or deletes their account must leave a past quarter's figures.

## 7. Versions

| Version | From | What changed |
|---|---|---|
| 1 | 20 November 2026 | First version (D-200). Amended 22 November 2026 before any report included agreed fees (D-201): agreed fees need 10 paid creators for any fee figure, and the p% rule (p = 10, against two who collude); asking prices unchanged, so the version stays 1 |
