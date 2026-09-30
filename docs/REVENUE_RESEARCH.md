# How we make money

**Researched 30 September 2026.** It builds on `docs/COMPETITIVE_LANDSCAPE.md` (21 September) and `docs/PLAYBOOK_GAPS.md` section 1, and goes further: what this market actually pays for, what the numbers mean for a one-city pilot, and a plan with checkpoints so we find out early if it is not working.

**Nothing here is decided.** Every price is a proposal to test with real brands, not a promise. Sources are at the bottom; most are industry articles and vendor pages, so treat single figures as a range, not a fact. Where something is our judgement, it says so. GST, TDS and invoicing rules are **needs validation pack** (`CLAUDE.md` constraint 6): a CA confirms them before anything is charged.

---

## 1. The answer, in six points

1. **Charge brands, never creators.** Creators are the supply, they are price-sensitive, and competitors lose them by charging. Brands already spend on this: the Indian market is about ₹3,000–3,500 crore in 2025, growing about 22% a year toward ₹4,500–5,000 crore by 2027.
2. **Do not take a cut of deals.** We never touch campaign money (constraint 1), so we could not collect a percentage without trusting both sides to report it. Marketplaces that live on a cut report losing 30–80% of it to deals moved off the platform. A fee we cannot collect is not a business model.
3. **Sell what nobody else sells: a deal you can trust.** Discovery is free now: Instagram's and YouTube's marketplaces take no cut. What stays unsolved is the deal itself: 60–90 day payment delays, fake followers, no record when something goes wrong. Indian small businesses already pay for trust: IndiaMART sells a trust badge for about ₹45,000 a year on top of listings.
4. **Three streams, in this order:** (a) **done-for-you campaigns** for local businesses, for cash and learning in the first months; (b) **monthly plans** for brands that post regularly; (c) **agency plans** for the agencies that already run Tamil Nadu campaigns. Pay-per-campaign fills the gap for shops that won't subscribe.
5. **Self-serve sign-ups alone will not pay the bills in one city.** Businesses that start free convert to paying at about 2–8% (median 4.5%). To reach 30 paying brands on sign-ups alone we would need about 670 free brands in one city. So the first revenue has to come from selling directly and from done-for-you work, while self-serve grows underneath.
6. **Decide in 90 days, from numbers.** Section 8 sets the checkpoints: if brands don't pay at the pilot prices by day 60, we change the price or the offer before spending more, instead of hoping.

---

## 2. What the market pays today

| Who charges | How | Price | Source |
|---|---|---|---|
| Indian influencer agencies | Percentage of creator spend | **15–30%** of spend | upGrowth, Jigsawkraft |
| Indian agencies, per project | Flat fee on top of creator payments | **₹75,000–3,00,000** a project | Jigsawkraft |
| Indian agencies, ongoing | Monthly retainer | **₹40,000–1,50,000** a month | Jigsawkraft |
| Indian influencer software | Subscription or commission | **₹25,000–3 lakh a month**, or **8–15%** | `COMPETITIVE_LANDSCAPE.md` |
| Collabstr (global marketplace) | Free with a 10% fee; paid plans cut the fee to 5% | **$299–399 a month** | Collabstr |
| Passionfroot (creator storefront) | Fee on each booking, paid by the brand | **5%** on the creator's own deals, **15%** on deals it brings | Passionfroot |
| IndiaMART (small-business listings) | Yearly plan for visibility, leads and a trust badge | **₹28,000–60,000 a year**, trust badge **₹45,000** | Vedain |
| Small-business software in India | Monthly plan | **₹499–1,999 a month** is common; tools that save real time or prevent a penalty sell at **₹1,500–5,000** | Salesvora, Rajesh R Nair |
| Instagram Creator Marketplace, YouTube Creator Partnerships | Discovery and outreach | **Free, no cut** | `COMPETITIVE_LANDSCAPE.md` |

**What the market is telling us** (our judgement from the table):

- **Money follows service.** Kofluence, largely a managed agency, reported **₹52.5 crore** revenue in FY25, up 28%. The pure software players publish less and charge enterprise prices. In India, people pay most readily for work done *for* them.
- **Discovery alone cannot be charged for.** Meta and YouTube give it away.
- **Small businesses pay yearly for visibility, leads and trust**, the IndiaMART pattern, not for "software".

### What a local business spends

Nano creators (1,000–10,000 followers) charge about **₹2,000–8,000 a post**, and in Tamil Nadu about ₹2,000–5,000 a Reel. A restaurant, salon or textile shop running three nano creators spends about **₹6,000–15,000 on creators** for one campaign. The same campaign through an agency's minimum project fee would cost ₹75,000 or more, so **agencies do not serve this customer at all**. That gap is ours.

---

## 3. What our constraints change

| Constraint | What it rules out | What it makes possible |
|---|---|---|
| **No funds** (constraint 1) | A cut of each deal; paying creators ourselves on a fixed cycle, which some platforms now offer | A neutral record both sides can trust *because* we have no money in the game. We charge **our own fees for our own service**, collected by a payment gateway; that is our revenue, never campaign money |
| **No guessed compliance** (constraint 6) | Charging before GST registration and invoicing are confirmed | Nothing, until the validation pack answers; it is on the critical path |
| **No personal data in embeddings** (constraint 2) | Selling creator data or contact lists | Aggregate, anonymous insight (for example a Tamil Nadu rate report), later |

**The honest risk:** some platforms now pay creators on a fixed cycle and chase the brand themselves, carrying the float. We cannot do that. Our answer has to be strong enough without it: a brand's public payment record, the reliability score, and a deal record nobody can quietly rewrite. If creators in the pilot choose "the platform pays me" over "a record", we will see it in the numbers (section 8).

---

## 4. The recommended model

### Stream 1 — Done-for-you campaigns (months 1–6: cash and learning)

A founder runs the whole campaign for a local business: finds three to five creators, agrees terms, checks delivery. The business pays the creators directly (constraint 1); **we invoice only our fee**.

- **Proposed fee to test:** a flat **₹2,999–4,999 a campaign**, or 15% of creator spend if higher. Far below an agency's ₹75,000 minimum, and it only works because our software does the paperwork.
- **Why first:** it earns from week one, needs no self-serve funnel, and is exactly the "concierge start" in `PLAYBOOK_GAPS.md` section 2: the software learns from every deal a founder runs by hand.
- **Limit:** it takes founder time. It is a bridge, not the business. Cap it (for example 15 campaigns a month) and move repeat customers to a plan.

### Stream 2 — Brand plans (from month 3: the core business)

| Plan (proposal) | For | Price to test | What it includes |
|---|---|---|---|
| **Free** | Trying it | ₹0 | One active campaign, the deal record and payment handshake, basic search |
| **Local** | Shops and restaurants | **₹999 a month**, or ₹9,999 a year | Three active campaigns, match suggestions, fair-rate guidance, reliability scores |
| **Growth** | D2C brands posting every month | **₹2,999 a month** | Unlimited campaigns, creator search with every filter, exports, priority support |
| **Agency** (stream 3) | Agencies running several brands | **₹7,999 a month** | Several brand workspaces, deal records per client, one bill |

**Pay per campaign** for businesses that won't subscribe: **₹499 a campaign** beyond the free one. It keeps the door open for the festival-only shop.

Why these numbers (judgement): Local sits inside the ₹499–1,999 band small businesses already pay; a year of Local (₹9,999) costs less than IndiaMART's cheapest listing; Growth is a tenth of what a monthly agency retainer costs; Agency undercuts the ₹25,000+ Indian tools. All four stay under **₹15,000**, the limit up to which UPI AutoPay renews without asking the customer again, so renewal is automatic for every plan.

**Rules that protect trust, whatever the price:**
- **Reliability scores, payment records and dispute history are never for sale** and never affected by what a brand pays. The day a score can be bought, the product is worthless.
- **Anything paid for is labelled.** A featured campaign says "Featured".
- **Creators never pay** to apply, to be seen, or to keep their record.

### Stream 3 — Agencies (from month 3)

Tamil Nadu already has agencies running Tamil campaigns (Social Beat and Influencer.in in Chennai, Zapplr, Katha IGNITE and others). They do not need discovery; they need **proof for their clients**: who delivered, who paid, what was agreed. An agency that brings eight brands is worth more than eight shops found one by one, and each agency is a sales channel. **Proposed:** the Agency plan above, plus a revenue share or discount for agencies that bring brands.

### Later (after the pilot proves the core)

- **Featured campaigns**, clearly labelled: ₹199–499 for a week at the top of a city's list.
- **Tamil Nadu creator rate report**, from anonymous, aggregated asking and agreed prices (never personal data): sold to brands and agencies before Pongal and Diwali.
- **Affiliate and commission tracking** for the commission campaign type, once link tracking is decided.
- **Creator Pro**, only if creators ask for it: paid extras such as invoices or a custom Passport link. The core Passport stays free forever.

### What we deliberately do not do

- A percentage of each deal (section 1, point 2).
- Charging creators to apply or to be listed.
- Selling contact details or creator data.
- Letting money change a score, a ranking without a label, or a dispute record.

---

## 5. The arithmetic

**Monthly costs once live:** about **₹25,000–35,000** (AWS about ₹15,000 for staging and production before credits, MSG91 ₹500 plus per-code costs, tools). AWS Activate credits can cover most of the AWS line in year one.

**Break-even is small.** Any of these covers ₹30,000 a month:

| Mix | Monthly revenue |
|---|---|
| 8 done-for-you campaigns at ₹3,999 | ₹31,992 |
| 30 Local plans at ₹999 | ₹29,970 |
| 4 Agency plans at ₹7,999 | ₹31,996 |

**A first real target, ₹1 lakh a month, by month 9 (proposal):**

| Stream | Count | Price | Monthly |
|---|---|---|---|
| Agency plans | 4 | ₹7,999 | ₹31,996 |
| Growth plans | 8 | ₹2,999 | ₹23,992 |
| Local plans | 25 | ₹999 | ₹24,975 |
| Done-for-you campaigns | 5 | ₹3,999 | ₹19,995 |
| **Total** | | | **₹1,00,958** |

**Why sign-ups alone are not enough.** Free-to-paid conversion for this kind of product runs 2–8%, median 4.5%. The 25 Local plans above would need about 550 free brands on the median rate: realistic across Tamil Nadu in a year, not in one city in three months. The table therefore leans on agencies and done-for-you work, which are *sold*, not waited for. A free trial of a paid plan (rather than a permanent free plan) converts better: opt-in trials run at about 14% median. **Test both** in the pilot.

**All prices before GST.** Whether GST is added on top and at what rate is a CA question (validation pack).

---

## 6. Why we could still fail, and what we do about it

| Risk | Early sign | What we do |
|---|---|---|
| **Not enough brands in one city** (the chicken-and-egg problem kills more marketplaces than anything else) | Fewer than 3 applications per campaign in 72 hours | Demand first: a founder sells 10–20 real campaigns before inviting creators in volume (`PLAYBOOK_GAPS.md` section 2) |
| **Brands meet creators once, then leave** | Repeat campaigns happen off the platform | Make staying worth it: the record, the score and fair rates only work on the platform; plans are priced so staying is cheaper than leaving |
| **Local shops won't pay monthly** | Local plan conversion under 2% | Lean on pay-per-campaign and done-for-you; move the monthly plan up to D2C brands |
| **Creators prefer platforms that pay them on a cycle** | Creators ask "who pays me?" in interviews | Lead with the brand's public payment record and the dispute trail; if it is not enough, this is a founder decision about the model, not something to work around |
| **Instagram adds deal tools** | Meta announces contracts or payments in Creator Marketplace | Our record and scores cross platforms and work for barter and local deals Meta ignores; move faster on agencies |
| **Growing too fast on borrowed money** | Spending ahead of revenue | Good Glamm Group, owner of the Plixxo and Winkl creator platforms, collapsed in 2025 from "too much, too fast, too big", leaving salaries and vendors unpaid. One city, revenue from month one, costs kept under ₹35,000 a month until revenue covers them |
| **Charging before invoicing is legal** | — | No invoice before the CA confirms GST and invoice rules (validation pack) |

---

## 7. What the backend needs, and when

None of this is approved; each is a gated decision (`CLAUDE.md` section 5).

| Step | What | Gates | When |
|---|---|---|---|
| 1 | **Nothing new for done-for-you.** It runs on today's API; the founder invoices by hand | None | Now |
| 2 | Plans and limits: a plan per brand, and limits checked when a campaign is posted | New table and a module (database, architecture) | Before month 3 |
| 3 | Taking payment for our plans: Razorpay subscriptions with UPI AutoPay, and its webhooks | New dependency, security, payments | With step 2 |
| 4 | GST invoices for our fees | Validation pack, then a table | Before the first charge |
| 5 | Agency workspaces: one agency managing several brands | Schema, authorization | Month 3–4 |
| 6 | Featured campaigns, labelled | Small; after the pilot | Later |

**The payment rule stays exact:** the gateway collects *our fee for our service*. It never touches a brand's payment to a creator, and none of the words constraint 1 forbids ever appear in the code or the copy.

---

## 8. The 90-day pilot, with checkpoints

**City:** one, Coimbatore or Madurai (a founder decision).

| By | Target (proposal) | If we miss it |
|---|---|---|
| Day 14 | **20 brand interviews** done, with the price questions below | Don't build billing; keep talking |
| Day 30 | **10 paid done-for-you campaigns**, **3 agencies** trying it | Lower the fee, or change who we sell to |
| Day 60 | **15 paying brands or agencies** on any plan; campaigns get **3 or more suitable applications in 72 hours** | Change the price or the offer before spending more on growth |
| Day 90 | **₹30,000 a month** in revenue (break-even); **40% of brands post a second campaign** | Stop and rethink the model with both founders |

### The interview (20 brands, 20 minutes each)

1. When did you last work with a creator? What did it cost, and what went wrong?
2. Have you paid a creator who didn't deliver, or been chased for a late payment?
3. How do you find creators today? What does that cost you in time?
4. If a service found three local creators, fixed the terms and checked delivery, what would you pay for that, per campaign?
5. Would you rather pay per campaign or a monthly amount? Which feels safer?
6. At ₹999 a month for three campaigns, would you try it this month? What would stop you?
7. Would a public record of which brands pay creators on time change anything for you?

The answers set the real prices. **Asking beats guessing:** the prices above are starting points, not conclusions.

---

## 9. Decisions needed from the founders

1. **The model:** the three streams above, or a different mix.
2. **Pilot prices,** after the 20 interviews.
3. **Whether the pilot charges from day one,** or runs free for the first campaigns (recommended: done-for-you is charged from day one; plans start charging at month 3).
4. **The pilot city,** and who does the done-for-you work.
5. **The CA:** GST registration and invoice rules before the first invoice (validation pack).

---

## Sources

Market size and money flows
- [Kofluence — revenue ₹52.5 crore FY25 (Inc42)](https://inc42.com/company/kofluence/)
- [Kofluence 2026 influencer marketing report](https://www.kofluence.com/influencer-marketing-research-report/)
- [Payment delays at major brands (Storyboard18)](https://www.storyboard18.com/brand-makers/payment-delays-plague-influencer-marketing-agencies-as-major-brands-lag-behind-77033.htm)
- [Influencer marketing gets institutionalised in 2026 (AgencyReporter)](https://agencyreporter.com/influencer-marketing-institutionalised-2026/)

Prices
- [Influencer pricing in India 2026 by tier (upGrowth)](https://upgrowth.in/influencer-marketing-pricing-india-2026/)
- [Influencer marketing cost in India 2026, agency fees (Jigsawkraft)](https://www.jigsawkraft.com/post/influencer-marketing-cost-in-india-complete-2026-pricing-guide)
- [Influencer marketing cost in India 2026 (Grynow)](https://www.grynow.in/blog/influencer-marketing-cost-in-india.html)
- [Collabstr pricing](https://collabstr.com/pricing) and [review (CreatorStackClub)](https://www.creatorstackclub.com/software/collabstr)
- [Passionfroot pricing (Help Center)](https://help.passionfroot.me/en/articles/11552638-pricing)
- [IndiaMART vs Justdial 2026: lead cost and plans (Vedain)](https://vedain.com/blog/indiamart-vs-justdial-which-lead-source-works-better-for-indian-smbs)
- [Best CRM for small business in India, ₹499–999 plans (Salesvora)](https://salesvora.com/blog/best-crm-for-small-business-in-india)
- [Building micro-SaaS in India 2026, willingness to pay (Rajesh R Nair)](https://rajeshrnair.com/blog/software/saas/build-micro-saas-india-2026-playbook.html)
- [Tamil Nadu influencer marketing (Zapplr Media)](https://zapplrmedia.com/influencer-marketing-agency-in-tamil-nadu)

Conversion, leakage, failure
- [Free-to-paid conversion benchmarks 2026 (knowledgelib)](https://knowledgelib.io/finance/saas-benchmarks/free-to-paid-conversion-benchmarks/2026)
- [SaaS conversion report (ChartMogul)](https://chartmogul.com/reports/saas-conversion-report/)
- [Marketplace leakage (Sharetribe)](https://www.sharetribe.com/marketplace-glossary/disintermediation-platform-leakage/) and [how to prevent it](https://www.sharetribe.com/academy/how-to-discourage-people-from-going-around-your-payment-system/)
- [How to kickstart and scale a marketplace (Lenny's Newsletter)](https://www.lennysnewsletter.com/p/how-to-kickstart-and-scale-a-marketplace)
- [The fall of Good Glamm Group (Inc42)](https://inc42.com/features/the-fall-of-good-glamm-group-how-the-house-of-brands-crumbled/) and [what triggered it (Outlook Business)](https://www.outlookbusiness.com/start-up/news/what-triggered-the-good-glamm-groups-collapse-ceo-darpan-sanghvi-opens-up)

Collecting our fees
- [UPI AutoPay vs card e-mandates, 2026 (Razorpay)](https://razorpay.com/blog/upi-autopay-vs-card-e-mandates/)
- [UPI AutoPay (Razorpay docs)](https://razorpay.com/docs/payments/payment-gateway/s2s-integration/recurring-payments/upi/?preferred-country=IN)

Free platforms
- [Instagram Creator Marketplace 2026 (Inrō)](https://www.inro.social/blog/instagram-creator-marketplace)
