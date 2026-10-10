# The billion-dollar gap: what the backend still needs

**Research of 8 October 2026, for Adhi.** Asked: "these are not enough; I am aiming for a billion-dollar company; do all the research." This file lists what the best platforms in the world and in India have, or are about to have, that we do not, and turns each gap into a backend item with its evidence, its fit with our rules, and what it needs before it can be built. **Every item here is proposed, not approved** (`CLAUDE.md` section 5). Section 3.8 of `docs/BACKEND_COMPLETE.md` carries them.

It builds on `docs/COMPETITIVE_LANDSCAPE.md` (version 3), which already covers the Indian and global competitors and what we have that they do not. Nothing there is repeated here.

---

## 1. First, the honest frame

- **The whole Indian market is small today.** Influencer marketing in India is estimated at **₹3,375 crore in 2026** (EY and Collective Artists Network), about US$400 million: the *entire* country's spend. A Tamil Nadu marketplace taking a fee on part of that is not a billion-dollar company on its own. The path there runs through all of India, then through what sits next to influencer marketing: **creator commerce** (India's D2C e-commerce is about **US$109 billion in 2026**, growing about 24% a year, Mordor Intelligence) and **software that small businesses pay for monthly**. How we earn is `docs/REVENUE_RESEARCH.md`, a founder decision.
- **Money for this category got scarce.** Influencer-platform companies raised **US$48.1 million across 18 rounds** in 2026 to September (Tracxn), against about US$807 million in the first five months of 2025 alone. The exits are going to whoever owns real workflow and data: **Accenture Song agreed to buy Whalar** (June 2026), the largest creator-economy deal to date. A company that wins now must be capital-efficient and own something others cannot copy.
- **Discovery is becoming free.** Meta's **Creator Marketing Hub** and YouTube's **Creator Partnerships** match brands and creators for nothing (`docs/COMPETITIVE_LANDSCAPE.md` section 3). Our moat is the part they do not do: **the deal, the proof, the payment record, and the compliance around them.** Every item below either deepens that moat or opens the next market.
- **Features do not make a billion-dollar company; customers do.** None of this replaces getting the first ten brands through real deals (`docs/GO_TO_MARKET.md`).

---

## 2. The gaps, as backend items

Size: S (days), M (one to two weeks), L (several weeks, or waits on an outside review). "Gate" is the approval `CLAUDE.md` section 5 needs first.

### A. Numbers the platforms themselves vouch for (the biggest gap)

Today every follower count and result is self-reported or read from a screenshot (D-055, D-070). The leaders read them from the platform, with the creator's permission.

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 29 | **Connected Instagram and YouTube accounts.** The creator signs in with Instagram (Instagram Login, `instagram_business_manage_insights`) and Google (`yt-analytics.readonly`); we read followers, reach, views and audience city, age and gender from the platform, dated and labelled "from Instagram". | Third-party access to insights needs **Meta App Review with business verification**; YouTube's sensitive scopes need **Google verification, 4 to 6 weeks**. Only Professional (Business or Creator) Instagram accounts have any API access. | Tokens are secrets: encrypted at rest, never in logs. Audience breakdowns are aggregate, never a follower's identity. Constraint 2 holds: nothing personal reaches an embedding. | Security, database, dependency; **L**. **Start the Meta and Google reviews as soon as the company exists**: they are the long lead. |
| 30 | **Results fetched, not read.** For a connected account, the deal's post insights (reach, views, saves) are fetched from the platform at proof time and sealed in the deal record, beside or instead of the screenshot reading. | Same APIs as 29. | Fetched only for posts submitted as proof on a deal, with the creator's connection. | After 29; **M**. |
| 31 | **Audience authenticity signals from real data.** Engagement-rate deviation from the creator's size band, engagement variance, sudden follower spikes: shown as facts with the method, never a hidden score. Replaces item 16's plan with a method. | A 100,000-account study (2026) found **37.2%** of influencer accounts show signs of inauthentic followers; engagement-rate anomaly identifies them with 82.6% accuracy; the 100k to 500k band is worst at 48.3%. | Facts with the method shown, as the delivery record does (D-038); never a verdict on a person. | After 29; **M**. |

### B. Paying, faster, without ever touching the money

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 32 | **Built 10 October (D-085), switched off until the consent notice exists.** **A UPI pay link on every payment.** The payment record offers a `upi://pay` link and QR with the creator's UPI ID, the agreed amount and the deal's reference; the brand's own UPI app opens with everything filled in, and the brand approves with its PIN. The reference comes back to us as the "mark paid" reference. | The link is NPCI's own linking specification; any UPI app opens it. Today a brand copies an amount and a UPI ID by hand, the most error-prone step in the deal. | **The money goes from the brand's bank to the creator's bank; it never passes through us** (constraint 1). But it means storing the creator's UPI ID, which `docs/standards/database.md` section 4 forbids without a founder decision, and DPDP consent. | **A founder decision on storing UPI IDs**, security, database; **M**. |
| 33 | **The barter tax tracker.** For each brand and creator, the running total of barter value in the financial year against the ₹20,000 mark where the brand must deduct 10% TDS (Section 194R, renumbered **393(1) Sl. 8(iv)** from 1 April 2026), shown to both before the line is crossed. | The threshold is per recipient per financial year, across all benefits; products count even if returned. Both sides get this wrong today. | A count of facts the deal record already holds; **the wording of any tax statement is the validation pack's** (constraint 6). | Validation pack for wording; **S**. |
| 34 | **Payment confirmed from the bank statement** (Account Aggregator). | RBI-recognised framework, 410 registered information users. | **Likely not open to us**: information users are regulated financial entities. Recorded here so nobody spends time on it; revisit through a licensed partner. | Research only. |

### C. Agreements with legal weight

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 35 | **Aadhaar eSign on the deal memo**, optional: both sides sign the agreed memo; the signed PDF's fingerprint joins the deal record. | Providers charge about **₹15 to ₹25 per signature**, less at volume (Leegality, SignYu, Digio). | Today the memo deliberately claims no legal force. Signing changes what it is: **a legal question for the validation pack**, and a vendor dependency. | Founders, legal, dependency; **M**. |

### D. Brands creators can trust

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 36 | **Verified business, from GST.** A brand enters its GSTIN; we check it against the GST register through a licensed provider (legal name, status, state) and show "GST-registered business, active", with the date checked. | GSTIN search is offered by GST Suvidha Providers; some offer free tiers of about 100 lookups. A creator's first fear is a brand that does not pay or does not exist (`docs/PSYCHOLOGY_AND_TRUST.md`). | A business's registration is public business data, not a person's. A check that fails says "could not confirm", never "fake". | Dependency, security; **S to M**. |

### E. Ads and usage rights

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 37 | **A usage-rights ledger**: for each deal, what the brand may do with the content (organic repost, partnership ads), from when, until when (from the memo's `usage_rights_days`), and whether the creator has granted Meta's partnership-ad permission or ad code; both sides see what expires and when. | Meta's Creator Marketing Hub (2026) brings permissions and partnership-ad creation into one workflow, adds a **Partnership Ads API**, and lets **AI agents manage creator permissions**. Brands running creators' content as ads is where the money moves next. | A record of what was agreed and granted. Enforcing it stays with Meta. | Database; **M**. Meta API integration later, after item 29's review. |

### F. Creator commerce (the bigger market)

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 38 | **Sales from commission deals.** Each commission deal gets its own tracked link and promo code; a **Shopify app** reports orders that used them, so both sides see sales, and the commission owed, as a record. | **121,624 active Shopify stores in India** (Q1 2026, up 32% a year); most funded D2C brands use it. ShopMy and LTK run on tracked links and commission rates the brand sets (10% to 30%). Commission is already one of our campaign types. | **We report sales and commission owed; the brand pays the creator directly**, as for any deal (constraint 1). Order data is the brand's; only counts and totals per code are kept. | Founders (commerce strategy), dependency (Shopify app review), database; **L**. |

### G. AI that removes work

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 39 | **Content pre-check before the brand reviews.** A draft or live post is checked against the memo's deliverables and the ASCI rules: disclosure up front and not hidden behind "more"; AI-generated content disclosed; **qualification shown before technical health or finance claims** (ASCI Addendum II). Flags go to both sides; nothing is blocked or judged automatically (D-024). | Brands using AI content scanning cut approval time by about **35%** (Sprout Social, 2025). ASCI's 2026 rules put fines of ₹10 to 50 lakh on undisclosed virtual influencers. | Our thin Claude interface (D-070), the same safeguards; the ASCI wording comes from the validation pack. | Validation pack (ASCI), dependency exists; **M**. |
| 40 | **A campaign brief from a few sentences.** A brand writes what it wants in its own words; Claude drafts the structured campaign (deliverables, cities, niches, budget band from fair-rate guidance) for the brand to edit. | GRIN rebuilt itself in 2026 around an AI agent ("Gia") that shortlists creators within 24 hours; Passionfroot leads with its agent ("Zest"). The empty form is where small brands give up. | Drafts only; the brand publishes. | Dependency exists; **S to M**. |
| 41 | **An MCP server**, so a brand's or creator's own AI assistant can read their deals and act within limits (needs item 11's scoped tokens). | MCP has over **97 million monthly SDK downloads** and support in ChatGPT, Claude, Gemini and Copilot; about **28% of Fortune 500** companies run MCP servers (early 2026); remote servers use OAuth 2.1. | Every action through the same API, rate limits and access checks; read-only first. | Security, architecture; **M**, after item 11. |

### H. Keeping brands and creators coming back

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 42 | **Built 10 October (D-084).** **Work together again in one tap**: a new memo from a finished deal's terms, sent to the same creator. It was built as a brand inviting a creator to an open campaign, with repeats as one kind of invitation. The "nothing new stored" below was wrong: four columns were added to `application`. | Repeat deals are where a marketplace's value compounds; "this creator delivered on time" is our own record (D-038). | Nothing new stored. | **S**. |
| 43 | **Campaign alerts for creators**: a saved city, niche and budget, and a notification when a matching campaign opens, held by D-079's rules. | Liquidity: a creator who hears first applies first. | Uses notification preferences (D-079). | Database; **S to M**. |
| 44 | **Counter-offers on quotes**: a brand answers an application's quote with another figure, and the creator accepts or declines, all on the record. | Negotiation happens today in WhatsApp, off the record. Part of item 17's structured deal notes. | Sealed in the deal record when it becomes a memo. | Database; **M**. |
| 45 | **Built 8 October (D-083).** **Availability**: a creator marks "booked until 20 Nov"; matching and search respect it. | Fewer applications that go nowhere, on both sides. | A date, nothing personal. | Database; **S**. |

### I. Agencies and larger brands

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 46 | **An agency workspace**: one agency managing several brands, each brand approving its own deals (beyond item 13's team seats). | Influencer.in (Chennai) manages about 2.5% of India's influencer spend for brands; Aspire and CreatorIQ sell to agencies at $795 to $3,000+ a month. Agencies are the fastest route to volume. | Each brand's deals stay its own; the agency acts on its behalf, logged. | Founders, security, database; **L**. |
| 47 | **A campaign report a brand can hand to its boss**: deals, deliverables, results, payments, and the deal-record fingerprints that prove it, as PDF and CSV. | Every enterprise platform sells reporting; ours can show proof nobody else has. | Only the brand's own deals; no creator's private details. | **M**. |

### J. Being trusted at scale

| # | Item | Evidence | Fits our rules | Gate, size |
|---|---|---|---|---|
| 48 | **Readiness for ISO 27001 or SOC 2**: our existing controls mapped to the standard's, gaps listed, evidence collected automatically from CI. | Enterprise and agency buyers ask for one before signing. | Builds on what exists (D-047's supply-chain controls, the admin log, Sentry). | Founders (cost and timing); **M** to map, the audit later. |
| 49 | **A public status page and published service levels**, fed by the health checks and tracing (item 3). | Expected of any product businesses depend on. | | Infrastructure; **S**. |

---

## 3. What to start first

**Long-lead, so start now (outside the code):** the company registration, then **Meta business verification and App Review** and **Google OAuth verification** (items 29 to 31, 37), and a **GST Suvidha Provider account** (36). These take weeks and nothing else can speed them up.

**Build first, in this order, once approved:**

1. **32, the UPI pay link.** It fixes the most error-prone step in every paid deal (needs the UPI ID decision).
2. **42 and 43**, repeat deals and campaign alerts. These are small and they drive liquidity.
3. **36, verified business from GST.** It answers the creator's first fear.
4. **39, the content pre-check.** It's the AI feature that saves real time, built on what exists.
5. **33, the barter tax tracker.** It's small, and both sides get the rule wrong today.
6. **29 to 31, verified data,** the moment the reviews clear.

**Then, once the pilot shows demand:** 38 (commerce), 46 and 47 (agencies), 37 (usage rights), 35 (eSign), 41 (MCP), 48 and 49.

---

## 4. Decisions this needs

1. May we store a creator's UPI ID, shown only to the brand on that creator's deal, for the pay link (item 32)? **(Adhi; validation pack for consent wording)**
2. Start Meta and Google platform reviews as soon as the company exists (items 29 to 31)? **(Adhi)**
3. Commerce (item 38): a direction for the company, not only a feature. **(Both founders)**
4. Signed memos (item 35): does a memo become a contract? **(Legal, via the validation pack)**

---

## Sources

- India market size: [Outlook Business, EY report](https://www.outlookbusiness.com/news/indias-influencer-marketing-industry-estimated-to-reach-rs-3375-crore-by-2026-report); [EY India](https://www.ey.com/en_in/insights/media-entertainment/how-influencer-marketing-is-impacting-brands-in-india)
- India D2C and Shopify: [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/india-d2c-ecommerce-market); [The State of Shopify in India 2026](https://emergedigital.co/the-state-of-shopify-in-india-2026/)
- Funding and exits: [Tracxn, influencer-marketing platforms](https://tracxn.com/d/trending-business-models/startups-in-influencer-marketing-platform/__4OVgHq5OlwgL6yR9nr68t0Y9RGUuCol27ROnaV0Frjo); [Creator Economy Funding News, September 2026](https://newmarketpitch.com/blogs/news/creator-economy-funding-news); [ContentGrip, creator-economy M&A 2026](https://www.contentgrip.com/notable-influencer-marketing-funding-rounds-and-acquisitions/)
- Instagram API access: [Instagram API integration guide 2026 (Phyllo)](https://www.getphyllo.com/post/instagram-api-integration-101-for-developers-of-the-creator-economy); [Instagram official APIs reference, April 2026](https://gist.github.com/jameschapman2c/65eff9f54a2d350b17a6ce5127b9fe42)
- YouTube API access: [YouTube OAuth scopes for creator data (Phyllo)](https://www.getphyllo.com/post/youtube-oauth-scopes); [YouTube Analytics API, channel reports](https://developers.google.com/youtube/analytics/channel_reports)
- Meta partnership ads: [Social Media Today](https://www.socialmediatoday.com/news/meta-expands-creator-partnership-opportunities-for-brands/807691/); [DesignRush, AI agents and creator permissions](https://news.designrush.com/meta-ai-agents-creator-permissions)
- Enterprise platforms and AI agents: [Storika, best platforms 2026](https://www.storika.ai/guides/best-influencer-marketing-platforms-2026); [Sprout Social, GRIN alternatives](https://sproutsocial.com/insights/grin-alternatives/)
- UPI linking: [UPI deep linking explained](https://www.dvaarik.com/blog/upi-payment-link-deep-linking-india); [NPCI UPI linking specification](https://www.labnol.org/files/linking.pdf)
- GSTIN verification: [Sandbox, Search GSTIN API](https://developer.sandbox.co.in/reference/search-gstin-api); [Masters India](https://www.mastersindia.co/gst-number-verification-api-bulk-utility/)
- Account Aggregator: [Setu](https://setu.co/data/financial-data-apis/account-aggregator/); [State of Account Aggregator 2026](https://casparser.in/blog/state-of-account-aggregator-2026/)
- eSign pricing: [SignYu pricing comparison](https://signyu.com/compare/pricing); [Aadhaar eSign India 2026](https://peko.one/in/blogs/company-formation/esign-in-india)
- Section 194R / 393: [Saral](https://saral.pro/blogs/tds-section-194r/); [Legal Suvidha](https://legalsuvidha.com/blog/tds-under-section-194r)
- ASCI 2026: [Legal 500, Addendum II](https://www.legal500.com/intelligence/india/media-telecoms-it-entertainment/asci-update-to-influencer-advertising-guidelines-qualification-mandatory-for-making-claims-related-to-technical-aspects-of-health-nutrition-and-finance); [Sansa Legal, 2026 guidelines](https://www.sansalegal.com/post/asci-influencer-advertising-guidelines-2026-disclosure-rules-for-paid-content-and-ai-influencers)
- AI content checks: [Influencers Time](https://www.influencers-time.com/ai-content-checks-cut-influencer-campaign-approval-time/)
- Creator commerce: [MakeInfluence, LTK and ShopMy explained](https://www.makeinfluence.com/en/academy/creator-commerce-apps-ltk-and-shopmy-vs-traditional-affiliate-networks)
- MCP adoption: [The state of MCP servers in 2026](https://tooldirectory.ai/blog/state-of-mcp-servers-2026); [MCP enterprise-managed authorization](https://blog.modelcontextprotocol.io/posts/enterprise-managed-auth/)
- Fake followers: [SociaVault, 2026 fake-follower study](https://sociavault.com/labs/reports/fake-follower-study-2026)
