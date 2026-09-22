# Competitive landscape

**Version 2, researched 21 September 2026.** It replaces the first pass from the same morning, which covered 8 platforms. This one covers about 20: Indian, global, and the free tools inside Instagram and YouTube. Every fact has a source at the bottom. Where something is our judgement rather than a fact, it says so. Where version 1 was wrong, section 9 says what changed.

**How to read it:** sections 1–2 are the conclusion. Section 3 lists who is out there. Sections 4–5 cover what they have that we lack, and what we have that they lack. Section 6 is the ranked list of what to build, each with the approval it needs.

---

## 1. The conclusion, in five points

1. **Discovery is now free and owned by the platforms.** Instagram's Creator Marketplace went worldwide at the end of January 2026, free, with no cut taken. YouTube relaunched Creator Partnerships in India in March 2026, with AI matching, media kits and creator rate cards built into YouTube Studio. Indian databases already list 1–7 million creators. **We should not compete on finding creators.**
2. **Neither Meta nor YouTube touches the deal itself.** Meta's marketplace leaves "payment, contracts, and usage rights" to "direct agreement between the brand and creator, not inside the platform". The terms, the delivery, the payment and what happens when one goes wrong: **that gap is our whole product.**
3. **Every competitor that deals with payment does it by moving the money.** Collabstr holds the brand's payment until delivery. Reelax, Influencer.in, Wobb and Kofluence process payouts. We never hold or move money (CLAUDE.md constraint 1). Our answer is a **record**: who paid on time, who delivered on time, and what each side said when it went wrong. **Nobody else publishes either half of that record.**
4. **The market's trust problem is enormous and measurable.** Payment cycles run 60–90 days. Two out of three Indian Instagram creators show fake-follower inflation. 42% of brands say they have paid an influencer later found to have heavy fake followings. Both sides price in the risk. A record of real behaviour is worth more here than anywhere.
5. **Nobody reviewed offers a Tamil-language product.** Qoruz and Reelax let a brand *filter* creators by 12 languages, and Social Beat, based in Chennai, runs Tamil campaigns as an agency. In every source reviewed, though, language is something to search by, never the language the product itself speaks. Tamil Nadu has 63 million internet users, and regional micro-creators earn 2–3× the engagement of metro macro-creators at about a tenth of the cost per post.

**Position, unchanged from version 1 and now better supported: Instagram and YouTube are where brands and creators meet. We are where the deal is kept honest.**

---

## 2. What "looks like a multi-million-dollar company" actually means here

This is our judgement. The research shows what the well-funded players compete on:

| What big platforms signal with | What it costs them | Where we stand |
|---|---|---|
| Huge creator databases (7M, 12M profiles) | Crawling, data deals, sales teams | **Deliberately not competing.** Meta and YouTube give this away |
| Live media kits, rate cards, instant analytics | Platform API integrations | Rate cards and media kit: **not built** (section 6, #1) |
| "Verified" badges and fraud screening | Third-party data | **Not built** (section 6, #6) |
| Handling payouts | Money-handling licences and liability | **Never**, by design |
| Speed, reliability, no lost work | Engineering discipline | **Built and measured:** worst p95 is 28% of budget; retries safe on every write; 1,052 tests; strict types |
| Trust you can check | Nobody has built it | **Built:** brand payment record, creator delivery record, neutral dispute record |

The honest summary: **polish is bought with money, but trust is built from facts.** On facts we are already ahead of everyone reviewed. On polish we are behind by design: the build order puts the frontend after the backend (D-004). The features in section 6 close the gap the frontend alone cannot.

---

## 3. Who is out there

### Free, inside the platforms (the real threat)

| Who | What it does | What it does not do |
|---|---|---|
| **Instagram Creator Marketplace** | Brands filter creators by audience demographics, engagement, niche and location, then invite them. **Free, no cut, worldwide since January 2026.** Adds an ad-performance prediction badge, similar-creator search, partnership ads (about 19% lower CPA), and native Reels affiliate links | Terms, payment, usage rights, proof and disputes are "handled separately through direct agreement" |
| **YouTube Creator Partnerships** (replaced BrandConnect, March 2026; live in India) | Gemini-powered brand–creator matching; creator **Media Kit**; **Desired Rates** for long-form and Shorts; **Open Calls**; paid-promotion disclosure; brand access to video metrics | The same gap: no record of whether anybody kept their side of the deal |

### India

| Who | Scale and model | Strongest feature | Gap we can use |
|---|---|---|---|
| **Reelax** | 1M+ verified creators, 4,000+ cities, 780 categories, **12 languages**; ranked No. 1 by Adgully (June 2026) | Fake-follower screening before creators appear in search; bulk payouts with zero commission | Gives brands **creators' direct phone numbers**. Moves money. No record of behaviour |
| **Qoruz** | 7M+ Indian creator profiles; regional-language filtering; powers **JioStarverse** | Audience intelligence; free influencer cost checker | Undisclosed annual pricing; marketer intelligence, not a deal-keeping system |
| **JioStarverse** (JioStar, 2025) | 500+ JioStar talent, AI insights, real-time tracking | Media-group scale and data | Marquee talent, not nano creators or local shops |
| **Influencer.in** (Social Beat, **Chennai HQ**) | 70,000+ verified influencers; manages about 2.5% of India's influencer spend | Full lifecycle: vetting, briefs, approvals, tracking, **payment processing**, reporting; Tamil and South Indian workflows | Agency-led; built for brands with agency budgets. **Our most direct competitor at home** |
| **Wobb** | 100,000+ creators, 600+ brands; app on Play and Indus stores | Barter, affiliate and small-cash campaigns; geotargeting; in-app chat; direct payouts; "Wobble" creator-to-creator collaboration; sales-tracking pixel | Moves money. No behaviour record |
| **Kofluence** | Marketplace model, AI matching, SMB-friendly | Fast campaign scaling | Discovery-first |
| **Winkl** | Micro and nano focus | Authenticity assessment, localised outreach | Campaign tooling only |
| **Plixxo** (POPxo) | 26,000+ creators; fashion, beauty, lifestyle | Niche benchmarking | Narrow niches |
| **Grynow** | Performance-based campaigns for startups | Pay-for-results framing | Performance tracking, not trust |
| **Chtrbox** | Since 2016; listed on BSE SME in late 2025 | Enterprise credibility | Enterprise pricing |
| **Collab** (parkyou) | App for Indian small businesses and creators | **District-level** creator filtering; paid or barter; restaurants invite local food creators | Discovery plus campaigns; no record of behaviour |
| **Katha IGNITE** | Tamil Nadu micro-creator "packs" | A Tamil creator roster, sold as an agency | A service, not a product |

**Indian pricing:** SaaS subscriptions of **₹25,000 to ₹3 lakh a month**, or **8–15% of campaign spend**. Qoruz does not publish its prices.

### Global

| Who | Model | Price | Feature worth copying |
|---|---|---|---|
| **Collabstr** | Open marketplace: creators list fixed-price packages, brands buy them | Free + 10% fee; $299–399/month plans at 5% | Creator **packages** with upfront prices; **influencer price calculator**; fake-follower checker; briefs with priced applications; one-click post analytics. Holds the brand's payment until delivery |
| **Passionfroot** | Creator "storefront": a live, bookable media kit | 15% take rate on its network; 5% on storefront bookings | **A media kit a brand can book through**, instead of a PDF sent over email |
| **Beacons** | Link-in-bio + media kit builder | Freemium | **Live** stats that update themselves |
| **Aspire / Upfluence / CreatorIQ** | Enterprise relationship and discovery suites | $795 to $3,000+/month | Enterprise reporting depth; not our market |

---

## 4. What they have that we do not

This list is honest: these are real gaps, not dismissals.

| Feature | Who has it | Should we? | What it needs |
|---|---|---|---|
| **Creator rate card and media kit** | YouTube (free), Collabstr packages, Passionfroot, Beacons | **Yes, first.** It is table stakes now that YouTube gives it away. It also makes the Passport link worth sharing | Creator columns (Erode Harish's track), a decision |
| **Audience size and verified stats** | Everyone | **Yes.** Without it fair-rate guidance would mislead | Self-reported first, clearly labelled; verified later via platform APIs |
| **Price guidance** | Collabstr calculator, Qoruz cost checker, YouTube Desired Rates | **Yes, better than theirs:** built from *agreed* fees on real deals, with sample size | Audience size first (above) |
| **Fraud / fake-follower screening** | Reelax, Collabstr, Winkl | **Yes, later.** India's fraud rate makes it valuable | Third-party data or platform APIs; cost decision |
| **Campaign results** (reach, engagement, sales) | Wobb pixel, Collabstr analytics, Influencer.in, JioStarverse | **Yes, minimal:** we already hold the proof links | Platform API decision (Instagram's Graph API needs the creator's login) |
| **In-app chat** | Wobb, Collabstr, Passionfroot | **Decide.** Brands and creators already live on WhatsApp (D-022 chose WhatsApp alerts) | Product decision: chat, or structured deal notes plus WhatsApp links |
| **Disclosure check at submission** | BigBang.Social compliance verifier; ASCI's own tool | **Yes, carefully.** We record the creator's confirmation today; checking the post is the next step | **Validation pack** (constraint 6), never invented; post access via API |
| **Affiliate / commission tracking** | Wobb, Instagram native affiliate | **Later.** The commission campaign type exists; tracking links do not | Decision on link tracking |
| **Creator-to-creator collaboration** | Wobb "Wobble" | **Later** (backlog E5, creator collectives) | Group applications need their own model |
| **AI matching** | Kofluence, YouTube (Gemini), JioStarverse | **Yes, Phase D**, but only *within our own marketplace* | Already planned; pgvector (Data track) |
| **Bulk payouts** | Reelax | **No.** We never move money. The equivalent we *can* build is bulk "mark paid" with reference matching | API only, no new table |

## 5. What we have that they do not

| Ours | Status | Why nobody else has it |
|---|---|---|
| **Brand payment record**: on-time share, median days to pay, unpaid deals, and debts owed now that "new" cannot hide | Built (D-034) | Platforms that move money have no reason to show a brand's record. Platforms that don't have no data |
| **Creator delivery record**: delivered, on time, disclosure confirmed, no-shows counted by the calendar | Built (D-038, D-039) | Collabstr has star reviews, which are opinions. Nobody records what actually happened |
| **Neutral dispute timeline** both sides can export | Built (D-035) | Others either judge disputes or have none |
| **Deal memo with an agreed date and an approval clock** | Built (D-024–D-026, D-039) | Contracts elsewhere are enterprise features |
| **Retry-safe on every write** (patchy 4G) | Built (D-040, branch `feature/retry-safety`) | Invisible, until a duplicate campaign or a false "already done" costs a user |
| **Consent-first public Passport**, no contact details | Built (D-036) | **Reelax hands out creators' phone numbers.** We never will |
| **Why-am-I-rejected feedback** with sample sizes | Built (D-041, branch `feature/application-feedback`) | Nobody tells creators the pattern behind their rejections |
| **No subscription, no commission** | By design | We never touch the money, so there is nothing to take a cut of. How we *do* earn is a founder decision, not yet made |
| **Tamil as the product's language** | Planned (frontend, after the backend) | Competitors treat language as a search filter |

---

## 6. What to build to beat them, ranked

Ranked by what it does for trust and for the small Tamil Nadu business, then by cost. **Nothing here is approved.** Each item says what it needs.

| # | Build | Beats | Needs |
|---|---|---|---|
| 1 | **Rate card and media kit on the Creator Passport**: packages with prices, audience size (labelled self-reported), and delivery and payment records attached. A brand sees price *and* proof of reliability on one link | YouTube Media Kit, Collabstr packages, Passionfroot storefront: none of them can show a *record* next to the price | Creator columns: **Erode Harish** and both founders |
| 2 | **Fair-rate guidance** from agreed fees on real deals, by niche, city and audience band, always with sample size and date | Collabstr's calculator and Qoruz's cost checker, which estimate; ours would be *observed* | #1's audience size; a decision on the minimum sample |
| 3 | **Payment reconciliation for busy brands**: bulk "mark paid", and matching of UPI references (RRN) against what brands claim | Reelax bulk payouts, with no money moved | API only; a decision on the matching rules (D-027 left room for it) |
| 4 | **Campaign results from proof links**: reach and engagement read back from the posts already on record | Wobb, Collabstr, Influencer.in analytics | Platform API decision; it closes deal → delivery → payment → *result*, which nobody else holds end to end |
| 5 | **Disclosure check at proof submission** | BigBang.Social's verifier | **Validation pack** (constraint 6), then post access |
| 6 | **Authenticity signals** (fake followers) | Reelax, Winkl, Collabstr | Third-party data; cost decision |
| 7 | **Matching within our marketplace** (Phase D) | Kofluence, YouTube, JioStarverse | Planned; Data track |
| 8 | **Tamil throughout** (frontend), plus Tamil WhatsApp templates | Everyone | Frontend phase (D-004); WhatsApp provider decision |

**What to deliberately not build:** an internet-wide creator database; anything that holds or moves money; exposing contact details; star ratings or reviews in place of the records (opinions can be bought, dated facts cannot); a subscription price wall for small businesses (the business model is a founder decision).

---

## 7. The problem we are built on

This still holds, and version 2 adds evidence:

- Payment cycles in Indian influencer marketing typically run **60–90 days**. Nano and micro creators are hit hardest, precisely who we serve.
- Creators who have been burned start **quoting higher prices or demanding deposits**. Brands already pay for late payment, as a risk premium.
- On the other side, **42% of brands** report having paid influencers later found to have heavy fake followings, and nearly two-thirds of Indian Instagram profiles show more than 60% fake followers.
- **Both sides are pricing in each other's risk.** A record of real behaviour lowers that price for everyone who behaves well. That is the commercial argument for this product.
- The market is growing about 25% a year toward **₹3,375–5,000 crore**, and **87% of Indian brands** keep a dedicated creator budget. South India is driving the shift to regional creators.

## 8. The compliance ground is moving

This is recorded for awareness, **not as rules for our product**: constraint 6 says compliance details come from the validation pack, never from research like this. According to the sources, ASCI updated its influencer guidelines for 2026:

- Disclosure is required for any material connection, including free products and affiliate commissions, not only payment.
- The disclosure is expected near the start of a caption, and within the first seconds of a video.
- AI and virtual influencers have specific rules.
- A platform's own "paid partnership" tag may not be enough on its own.
- Monitoring and penalties are increasing.

Our `disclosure_confirmed` records the creator's statement. Whether that is enough is a validation-pack question.

## 9. What changed since version 1

| Version 1 said | Version 2 finds |
|---|---|
| "Nobody is serving regional-language creators properly" | **Too strong.** Qoruz and Reelax filter by up to 12 languages, and Social Beat runs Tamil campaigns. The gap is narrower but real: *language as the product's language*, not as a filter |
| 8 competitors | About 20, including **YouTube Creator Partnerships**, **Reelax** (No. 1 in India, June 2026), **Influencer.in** (Chennai), **Wobb**, **JioStarverse**, **Collab**, **Passionfroot** |
| Global platforms cost $795–3,000/month | Indian ones too: ₹25,000 to ₹3 lakh a month, or 8–15% commission |
| Creator delivery record was the top recommendation | **Built** (D-038), and the undated-deal loophole closed (D-039) |

---

## Sources

Version 2:

- [Instagram Creator Marketplace — brand guide, partnership ads and API (2026)](https://www.storika.ai/guides/instagram-creator-marketplace)
- [Instagram Creator Marketplace — what it is (2026)](https://www.inro.social/blog/instagram-creator-marketplace)
- [Instagram Reels native affiliate commerce (2026)](https://joinbrands.com/blog/instagram-shop-2026/)
- [YouTube Creator Partnerships replaces BrandConnect in 7 markets](https://ppc.land/youtube-creator-partnerships-replaces-brandconnect-in-7-markets/)
- [YouTube Creator Partnerships — India help page](https://support.google.com/youtube/answer/9385307?hl=en&co=GENIE.CountryCode%3DIN)
- [Reelax — platform](https://getreelax.com/), [verified database](https://getreelax.com/find-influencers/), [payouts](https://getreelax.com/influencer-payouts/)
- [Top 10 influencer marketing platforms in India (Adgully, 2026)](https://www.adgully.com/post/17224/top-10-influencer-marketing-platforms-in-india-2026)
- [JioStar launches JioStarverse](https://www.exchange4media.com/digital-news/jiostar-launches-jiostarverse-a-data-led-influencer-marketing-platform-143219.html), [powered by Qoruz](https://mediabrief.com/jiostar-launches-jiostarverse/)
- [Social Beat — influencer marketing](https://www.socialbeat.in/influencer-marketing/), [company profile](https://www.crunchbase.com/organization/social-beat), [Influencer.in](https://www.influencer.in/)
- [Wobb on Google Play](https://play.google.com/store/apps/details?id=ai.wobb&hl=en_US), [Wobb on Capterra](https://www.capterra.com/p/10009964/Wobb/)
- [Kofluence on the App Store](https://apps.apple.com/in/app/kofluence-influencer-platform/id1488194664)
- [Collab — for Indian businesses and creators](https://collab.parkyou.in/)
- [Katha IGNITE — Tamil Nadu micro-influencers](https://katha-ads.com/blog/top-10-micro-influencers-in-tamil-nadu-and-the-tamil-creator-pack/)
- [Top 15 influencer marketplaces in India (DGTLmart)](https://dgtlmart.com/blog/top-15-influencer-marketplaces-in-india-2025/)
- [Qoruz pricing](https://qoruz.com/pricing), [Qoruz review and pricing](https://ainfluencer.com/qoruz/)
- [Influencer pricing in India, 2026](https://upgrowth.in/influencer-marketing-pricing-india-2026/)
- [Collabstr on Capterra](https://www.capterra.com/p/203391/Collabstr/), [Collabstr review 2026](https://ainfluencer.com/collabstr/)
- [Passionfroot for creators](https://www.passionfroot.me/creators), [Passionfroot review](https://www.creatorstackclub.com/software/passionfroot)
- [Beacons media kit builder](https://beacons.ai/i/app-pages/media-kit)
- [Regional creators and South India (afaqs)](https://www.afaqs.com/news/advertorial/indias-influencer-marketing-is-racing-toward-3375-crore-and-south-india-is-driving-the-shift-to-regional-creators-12144842), [₹5,000 crore led by regional stars (Deccan Chronicle)](https://www.deccanchronicle.com/business/indias-influencer-marketing-boom-industry-nears-5000-crore-as-regional-creators-rise-1970876)
- [Fake followers among Indian influencers (Business Standard)](https://www.business-standard.com/india-news/what-part-of-insta-influencers-followers-are-fake-answer-will-shock-you-124041900840_1.html), [Fake followers in India, 2026](https://gmtalentsnetwork.com/fake-followers-in-india/), [Influencer fraud statistics 2026](https://autofaceless.ai/blog/influencer-fraud-statistics-2026)
- [ASCI influencer disclosure tool](https://www.ascionline.in/social/tools/), [ASCI 2026 guidelines explained](https://www.sansalegal.com/post/asci-influencer-advertising-guidelines-2026-disclosure-rules-for-paid-content-and-ai-influencers)
- [Influencer marketing in India, 2026 (Board Infinity)](https://www.boardinfinity.com/blog/influencer-creator-marketing-2026/)

Carried from version 1:

- [India's creator economy: broken payments as the bottleneck](https://www.thereelstars.com/tech/indias-creator-economy-is-booming-but-broken-payments-are-becoming-its-biggest-bottleneck/)
- [Creator payment SLAs: fixing late pay](https://www.influencers-time.com/creator-payment-slas-fixing-late-pay-before-it-costs-you/)
- [Collabstr vs Aspire vs CreatorIQ, 2026](https://collabstr.com/blog/collabstr-vs-aspire-vs-creatoriq)
- [Influencer platform cost comparison](https://collabstr.com/blog/influencer-marketing-platforms-cost-comparison-upfluence-alternatives)
