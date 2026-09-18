# What the playbook does not cover

The Product, Design & Build Playbook v1.0 (17 September 2026) answers: what the market looks like on Android, which features set us apart, how the product should look and behave, and what to build it with. It does that well, and this file does not repeat it.

This file covers the rest of what a business like this needs before launch. Everything here is a **proposal for founder decision**, never a decision already taken. Recorded decisions live in `docs/DECISIONS.md`; build order lives in `docs/PRODUCT_BACKLOG.md`.

**Two rules apply to every line below.** We never receive, pool or hold campaign money: brands pay creators directly and we record what happened. And we never invent compliance: anything marked **needs validation pack** must be answered by a qualified source before it is built.

---

## 1. How we make money

The playbook mentions "free for creators, 14-day brand trial" as an idea borrowed from a competitor. It does not say how the business earns.

| Option | How it works | Fits us because | Risk |
|---|---|---|---|
| Brand subscription | A monthly fee per brand, with campaign limits by tier | Predictable; no per-deal cut; nothing to reconcile | Small local shops may not commit monthly |
| Success fee invoiced to the brand | A percentage of an agreed deal, invoiced by us after both sides confirm | Aligned with value delivered | We must detect deals completed off-platform |
| Listing fee per campaign | A flat fee per posted campaign | Simple for a shop spending ₹2–5K | Discourages posting, which is our supply of demand |
| Paid placement | Brands pay to feature a campaign; creators are never charged | Keeps creators free | Must be labelled clearly, or trust suffers |

**Recommendation:** free for creators forever, a **listing fee per campaign for local businesses** plus a **monthly plan for regular brands**, and no percentage cut in the pilot. A cut requires us to track money we never touch, which invites exactly the disputes we are trying to remove.

**Decisions needed:** pricing model, pilot prices, whether the pilot charges at all, and how we invoice (**needs validation pack** for GST).

---

## 2. Getting the first users (both sides)

A marketplace with creators and no campaigns is dead, and the reverse is worse. The playbook names the growth features but not the seeding plan.

- **One city first.** Pick Madurai or Coimbatore, not both. Depth beats spread.
- **Demand before supply.** Ten to twenty real campaigns waiting before we invite creators in volume, even if the first ones are hand-sold by a founder.
- **Concierge start.** For the first 50 deals, a founder runs matching by hand and watches every handshake. The software follows what works.
- **Creator supply:** the free Creator Passport aimed at creators left behind by the competitors that shut down, plus city leaderboards and referrals.
- **Brand supply:** local business associations, shop owners' groups, wedding and food clusters, and small agencies that already manage several shops.
- **Fill rate is the health metric**: the share of campaigns receiving at least three suitable applications within 72 hours.

**Decisions needed:** launch city, the pilot's target counts for each side, and who does the concierge work.

---

## 3. What we measure

The playbook sets performance budgets, not product metrics.

| Level | Metric | Why |
|---|---|---|
| North star | Completed deals with a confirmed payment, per month | It is the only event where both sides got what they came for |
| Liquidity | Campaign fill rate; time to first application; share of creators with a first deal within 30 days | Marketplace health |
| Trust | Median days from "marked paid" to "confirmed received"; dispute rate; share of deals completed without support contact | This is our whole positioning |
| Funnel | Sign-up → profile complete → first application → first deal → second deal | The second deal matters more than the first |
| Quality | Applications per campaign that the brand rates useful; rejection reasons given | Guards against spam applications |
| Support | First response time; tickets per 100 deals, in Tamil and English separately | Kofluence's failure was support, not features |

**Rule:** every number shown to a user carries its sample size and date. If there is not enough data, the app says so instead of inventing precision.

---

## 4. The backend architecture the playbook assumes

The playbook chooses frontend frameworks and tools. It does not define the system underneath. This repository is that system, and these are the pieces still to design (see `docs/PRODUCT_BACKLOG.md` for order):

- **State machines** for application, deal memo, payment status and dispute, each written down with the allowed transitions, who may make each one, and a test per blocked transition.
- **An event record** that every state change appends to, so history is reconstructable and the reliability score is computed from evidence, not from a mutable column.
- **Repeat-proof writes** (`Idempotency-Key`) for anything that creates a payment record or sends a message, which is what makes retries safe on patchy 4G.
- **One media pipeline** for proof uploads: where files live, virus and type checks, size limits, resumable uploads, and links that expire.
- **Notifications** behind one interface with retries, a failure state a human can see, and no personal data in logs.
- **A public read API and webhooks**, once the contract is stable, for agencies managing many brands.
- **A search and discovery contract** that returns the reasons behind results, not only a ranked list.

**Decisions needed:** media storage, job runner, and whether the pilot exposes any public API.

---

## 5. Payments, without ever holding money

The playbook covers the UPI link and reference matching. The policies around them are missing, and they decide how disputes go.

- **Milestones or single payment?** Recommendation: single payment on approved proof for the pilot, with an optional advance recorded as a separate entry.
- **What counts as proof** of a deliverable, and how long a brand has to approve it. Recommendation: 5 working days, then automatic approval, with every step timestamped.
- **Cancellation:** who may cancel, when, and what the creator is owed for work already done.
- **Late payment:** when a deal counts as late, what the creator sees, and how lateness affects the brand's reliability score.
- **Reliability score rules, published in plain words:** what counts, the minimum number of deals before a score shows, how old data ages out, and the brand's right to reply. The playbook's own risk table asks for this.
- **Dispute path:** raise, evidence from both sides, a decision by us, and what "decided" means when no money passed through us.

**Decisions needed:** all of the above. **Needs validation pack:** invoices, GST and TDS treatment for both sides.

---

## 6. Trust and safety

The playbook mentions fraud detection once. In this market it is the product.

- **Identity checks:** what a creator must prove, what a brand must prove, and what changes when either refuses. **Needs validation pack** for what we may collect and keep.
- **Fake audience detection:** which signals we record, always with the reason shown to the creator and an appeal path. Never a silent block; unexplained blocks are the loudest complaint in the playbook's own research.
- **Off-platform leakage:** people will try to finish deals in direct messages. Recommendation: make staying worthwhile (reliability score, proof record, invoices) rather than policing it.
- **Abuse and harassment:** reporting, blocking, and what happens to a deal already in progress.
- **Brand safety:** categories we refuse (alcohol, tobacco, betting, loan apps, adult), decided once and enforced at campaign creation. **Needs validation pack** for advertising rules.
- **Minors:** creators under 18 exist. Whether we allow them, and under what conditions, is a legal question. **Needs validation pack.**

---

## 7. Support and operations

- **Channels:** in-app tickets, WhatsApp, and a response promise we can keep. Tamil support is part of the positioning, not an extra.
- **Response targets:** first response within one working day for normal issues, within four hours for anything about a payment.
- **An operations console** for the team: find an account, read a deal's timeline, resolve a dispute, fix a stuck state. This is real backend work, and every action is recorded with who did it.
- **Runbooks** for the common failures: message provider down, database slow, a stuck migration, a suspected leak.
- **Status page** so people are not left guessing.

**Decision needed:** who is on support, in which hours, in the pilot.

---

## 8. Data, privacy and records

- **Data map:** every piece of personal data we hold, why we hold it, who can see it, and how long it stays. **Needs validation pack** for retention.
- **Consent** at sign-up, in Tamil and English, for each distinct purpose.
- **Export and deletion** that a user can do themselves, with a clear statement of what deletion does to deals that already happened.
- **Access control inside the team:** who can read contact details, and a log of when they did.
- **Audit record** for every action taken by our staff on someone's data.

---

## 9. Running it reliably

- **Environments:** local, staging, production, with production data never copied down.
- **Deployment:** where it runs, how a release is rolled back, and migration safety (expand, migrate, contract).
- **Backups:** daily, with **one restore actually tested** before launch, plus a stated recovery point and recovery time.
- **Availability target** for the pilot: 99.5% during Indian daytime, measured, with alerts to a person.
- **Cost ceiling** per month and an alert at 80% of it.

**Decisions needed:** hosting platform, availability target, monthly budget.

---

## 10. Security programme

- **A written threat model** for the main flows: login, deal memo, payment confirmation, media upload.
- **Key rotation** and what happens if a key leaks.
- **Dependency and vulnerability checks** in CI, blocking high findings.
- **An outside security review** before taking real users' data at scale, and a way for anyone to report a vulnerability.
- **Access to production** limited and logged.

---

## 11. Anything with AI in it

- **Matching must be measurable:** a labelled sample, a target for how often the right creators appear, and a check that it does not always favour the same people.
- **Explanations** with every match, and guidance a creator can act on.
- **Any compliance checker is advisory only.** It flags a likely problem; a person decides. **Needs validation pack** for ASCI rules.
- **Voice and translation:** what happens to a recording, how long it is kept, and confirmation before anything is sent to a third party.
- **No personal data in embeddings.** Enforced by a test, not by a habit.

---

## 12. Language, beyond translation

- **A glossary** of product terms in Tamil, agreed once, so "campaign", "deal memo" and "payment confirmed" never drift.
- **A fluent reviewer** signs off every string before release, as the playbook requires for copy.
- **Tanglish is normal**, and search must cope with it: people will type Tamil words in English letters.
- **Formats:** Indian digit grouping (₹1,50,000), Indian date order, and 12-hour times.

---

## 13. After v2

The playbook's phases stop at v2. Worth naming now, so today's decisions do not block them:
- more Tamil Nadu cities, then neighbouring states, which makes language a first-class setting rather than a toggle;
- agencies managing many brands, which needs a team account model;
- campaign results and return on investment, which needs the event record from section 4;
- a partner API, which needs a stable contract and versioning from the start.

---

## 14. Risks the playbook's risk table does not list

| Risk | Why it matters | Mitigation |
|---|---|---|
| Deals move off-platform after the first introduction | Kills the record, the score and the revenue | Make staying valuable: proof record, invoices, reliability score |
| Cold start on both sides | The classic marketplace failure | One city, demand first, concierge matching |
| A payment dispute with no money trail | We never hold funds, so evidence is everything | Reference matching, timestamps, an evidence timeline |
| Message provider costs or template rejections | The whole WhatsApp workflow depends on it | Start with notifications only; keep SMS as a fallback |
| One founder being the only support | Support failure is what sank the leading competitor | Response targets, ticket tooling, and a second person |
| Personal data leak | Trust ends immediately | Data map, least access, audit record, outside review |

---

## 15. The decisions this file asks for

| # | Decision | Blocks |
|---|---|---|
| 1 | Money amounts: whole paise or decimal | The first campaign budget field |
| 2 | Pricing model and pilot prices | Any billing work |
| 3 | Launch city and pilot targets | Seeding plan and seed data |
| 4 | Campaign types in the pilot | The campaign table |
| 5 | Proof, approval window, cancellation and late-payment policy | Deal memo and payment status |
| 6 | Reliability score rules, including the minimum deals before it shows | The score |
| 7 | Dispute process and who decides | Dispute work |
| 8 | Identity checks for each side | Onboarding |
| 9 | Refused campaign categories | Campaign creation |
| 10 | Media storage and job runner | Uploads, notifications, reminders |
| 11 | Hosting, availability target, monthly budget | Deployment |
| 12 | Support channels, hours and response targets | Launch readiness |
| 13 | Validation pack answers: DPDP retention and consent, ASCI rules, GST and TDS, minors, advertising restrictions | Everything marked above |
