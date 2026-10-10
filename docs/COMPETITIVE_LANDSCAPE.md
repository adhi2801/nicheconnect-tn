# Competitive landscape

**Version 4, 10 October 2026.** Version 2 (21 September) researched about 20 platforms: Indian, global, and the free tools inside Instagram and YouTube. Version 3 (1 October) re-checked the market and turned the build list into novelties. Version 4 brings every status in line with what was built from 8 to 10 October: invitations, availability, scam protection and the UPI pay link. Every fact has a source at the bottom. Where something is our judgement rather than a fact, it says so. Section 9 says what changed in each version.

**How to read it:** sections 1–2 are the conclusion. Section 3 lists who is out there. Section 4 closes every gap they have over us; section 5 is what we have that they lack. Section 6 is the novelties next: things nobody has, each with the approval it needs.

---

## 1. The conclusion, in five points

1. **Discovery is now free and owned by the platforms.** Instagram's Creator Marketplace went worldwide at the end of January 2026, free, with no cut taken. YouTube relaunched Creator Partnerships in India in March 2026, with AI matching, media kits and creator rate cards built into YouTube Studio. On **15 September 2026 Meta took its Creator Marketing Hub worldwide**, with a messaging API for outreach, Facebook creators in the same API, and creator search through Meta's AI business assistant. Indian databases already list 1–7 million creators. **We should not compete on finding creators.**
2. **Neither Meta nor YouTube touches the deal itself.** Meta's marketplace leaves "payment, contracts, and usage rights" to "direct agreement between the brand and creator, not inside the platform". The terms, the delivery, the payment and what happens when one goes wrong: **that gap is our whole product.**
3. **Every competitor that deals with payment does it by moving the money.** Collabstr holds the brand's payment until delivery. Reelax, Influencer.in, Wobb and Kofluence process payouts. We never hold or move money (CLAUDE.md constraint 1). Our answer is a **record**: who paid on time, who delivered on time, and what each side said when it went wrong. **Nobody else publishes either half of that record.**
4. **The market's trust problem is enormous and measurable.** Payment cycles run 60–90 days. Two out of three Indian Instagram creators show fake-follower inflation. 42% of brands say they have paid an influencer later found to have heavy fake followings. Both sides price in the risk. A record of real behaviour is worth more here than anywhere.
5. **Local, not by language any more.** Version 2 found nobody offering Tamil as the product's own language. On 23 September we chose English only (D-054), so that separation is given up, knowingly. What stays local is presence: one city made dense first (`docs/GO_TO_MARKET.md`), Indian formats, and a record of local deals. Regional micro-creators still earn 2–3× the engagement of metro macro-creators at about a tenth of the cost per post.

**Position, unchanged from version 1 and now better supported: Instagram and YouTube are where brands and creators meet. We are where the deal is kept honest.**

---

## 2. What "looks like a multi-million-dollar company" actually means here

This is our judgement. The research shows what the well-funded players compete on:

| What big platforms signal with | What it costs them | Where we stand |
|---|---|---|
| Huge creator databases (7M, 12M profiles) | Crawling, data deals, sales teams | **Deliberately not competing.** Meta and YouTube give this away |
| Live media kits, rate cards, instant analytics | Platform API integrations | Rate cards and media kit **built** (D-055); results read from proof **built** (D-070) |
| "Verified" badges and fraud screening | Third-party data | **Open**: built from observed reach on real deals instead of bought data (section 4) |
| Handling payouts | Money-handling licences and liability | **Never**, by design |
| Speed, reliability, no lost work | Engineering discipline | **Built and measured:** retries safe on every write; over 2,500 tests at about 98% coverage, each critical rule shown to fail when broken; API fuzzing; strict types; budgets in `docs/PERFORMANCE.md` |
| Safety from scams | Trust and safety teams (Upwork and Fiverr flag off-platform moves and check links) | **Built in the product:** money requests and early contact details flagged, links only to known hosts, daily ceilings, invisible blocking (`docs/standards/trust-and-safety.md`) |
| Trust you can check | Nobody has built it | **Built:** brand payment record, creator delivery record, neutral dispute record, and a deal record nobody can quietly change (D-057, D-060) |

The honest summary: **polish is bought with money, but trust is built from facts.** On facts we are already ahead of everyone reviewed. On polish we are behind by design: the build order puts the frontend after the backend (D-004), and `docs/standards/frontend.md` sets the bar it must meet. The novelties in section 6 widen the lead on facts.

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

## 4. Closing every gap: beaten, not matched

**Updated 10 October 2026, status checked against the code.** The goal is not
to be one more platform with the same list. Every feature a competitor has is
a gap to close **with something theirs cannot do**, or a deliberate refusal
for a stated reason. Matching them is the floor, never the target.

| Their feature | Who has it | Us, today | How ours beats theirs | What is left |
|---|---|---|---|---|
| **Rate card and media kit** | YouTube, Collabstr, Passionfroot, Beacons | **Closed** (D-055) | Price **and** the creator's delivery and payment record on one link; theirs show a price with nothing behind it | Nothing |
| **Price guidance** | Collabstr calculator, Qoruz, YouTube Desired Rates | **Closed, step 1** (D-056) | Published prices, five creators or nothing, with the sample size shown; theirs are estimates | Step 2: agreed fees from real deals, which only we hold |
| **Bulk payouts** | Reelax | **Closed, our way**: bulk "mark paid" with payment references | The same speed for a brand paying many creators, without us ever touching the money, so no licence, no float, no risk to the creator | Nothing. Moving money stays refused (constraint 1) |
| **AI matching** | Kofluence, YouTube (Gemini), JioStarverse | **Closed, both ways** (Phase D) | Every match says **why**: shared niches, city, accepted deals; theirs are black boxes | Nothing |
| **Audience size and stats** | Everyone | **Half**: self-reported, dated, labelled (D-055) | A number with its date and its source, never passed off as verified | Observed numbers from proof (below), then platform-verified |
| **Campaign results** | Wobb, Collabstr, Influencer.in, JioStarverse | **Closed, switched off** (D-070) until the validation pack allows a processor | Read from every proof, checked against the creator's own claims, **sealed** so nobody changes them later. Nobody has results inside a tamper-evident deal record | The validation pack; then *stated against observed* on the Passport (section 6) |
| **Inviting a creator** | Instagram Creator Marketplace, impact.com, Skeepers | **Closed** (D-084) | A repeat of an earlier deal arrives with its memo already drafted from the agreed terms; a creator declines with a reason the brand sees; 25 unanswered invitations per campaign and 100 a day per brand stop spraying; a block ends it for good | Nothing |
| **Bookable availability** | Passionfroot (bookable slots) | **Closed, our way** (D-083) | One "booked until" date that search and matching rank by, rather than a calendar a reel creator does not keep | A slot calendar, only if pilot creators ask |
| **Scam protection** | Upwork, Fiverr | **Closed** (items 57 to 60) | Built into each feature, not a moderation queue: flags on fee requests and early contact details, links only to known hosts, invisible blocking | Nothing |
| **Paying the creator conveniently** | Collabstr, Reelax, Wobb (they move the money) | **Closed, our way, switched off** (D-085) until the consent notice exists | A UPI pay link opens the brand's own app, so the money goes bank to bank and never through us: no licence, no float, no risk | The validation pack's notice; a real-phone test |
| **Fake-follower screening** | Reelax, Collabstr, Winkl | **Open** | Planned to go further: not a score bought from a data vendor, but observed reach on real deals against stated reach (from results, above), which a bought follower cannot fake | Results first, then a decision on outside data |
| **Disclosure check** | BigBang.Social, ASCI's tool | **Half**: the creator's confirmation is recorded | Checked at proof time and sealed with the proof, so a dispute shows what was declared | **Validation pack** (constraint 6) |
| **In-app chat** | Wobb, Collabstr, Passionfroot | **Open** | Planned: structured deal notes that join the deal record, so what was agreed is provable, plus WhatsApp for the talk itself. Their chats prove nothing | A product decision |
| **Affiliate and sales tracking** | Wobb pixel, Instagram affiliate | **Open** | Planned: commission deals (already a campaign type) with sales sealed in the record, so a brand cannot under-report and a creator cannot over-claim | A decision on link tracking |
| **Creator collaborations** | Wobb "Wobble" | **Open** (E5) | Planned: group deals where each creator's delivery and payment stays individually on record; theirs blur who delivered | A model for group applications |

**Score on 10 October 2026:** of fifteen, **nine closed** (two of them built
and switched off until the validation pack answers), two half, four open. On
1 October it was four closed of eleven. Every open one has a stated way to
beat, not match.

## 5. What we have that they do not

Status checked against the code, 10 October 2026.

| Ours | Status | Why nobody else has it |
|---|---|---|
| **Brand payment record**: on-time share, median days to pay, unpaid deals, and debts owed now that "new" cannot hide | Built (D-034) | Platforms that move money have no reason to show a brand's record. Platforms that don't have no data |
| **Creator delivery record**: delivered, on time, disclosure confirmed, no-shows counted by the calendar | Built (D-038, D-039) | Collabstr has star reviews, which are opinions. Nobody records what actually happened |
| **A deal record nobody can quietly change**: append-only, chained, stamped daily by outside timestamp authorities, checkable by anyone with the export | Built (D-057, D-060) | Every competitor's history is rows it can edit |
| **Proof as files, cleaned of location and hidden data, sealed in the record** | Built (D-065, D-066, D-067) | Others keep files as uploaded, or keep links that die with the post |
| **Results read from proof, checked against the creator's own claims, sealed** | Built, switched off until the validation pack (D-070) | Results elsewhere need a platform connection or an agency; nobody checks them against the creator's stated reach |
| **Neutral dispute timeline** both sides can export | Built (D-035) | Others either judge disputes or have none |
| **Deal memo with an agreed date and an approval clock** | Built (D-024–D-026, D-039) | Contracts elsewhere are enterprise features |
| **Matching that explains itself, both ways** | Built (Phase D) | Kofluence, YouTube and Meta match with a black box |
| **Fair-rate guidance**: published prices, five creators or nothing | Built (D-056) | Calculators elsewhere estimate |
| **Retry-safe on every write** (patchy 4G) | Built (D-040) | Invisible, until a duplicate campaign or a false "already done" costs a user |
| **Consent-first public Passport**, no contact details | Built (D-036) | **Reelax hands out creators' phone numbers.** We never will |
| **Why-am-I-rejected feedback** with sample sizes | Built (D-041) | Nobody tells creators the pattern behind their rejections |
| **Records that say how broad they are**: how many different brands or creators a record rests on | Built (item 61) | A perfect record from one partner is how records are faked; nobody else shows the breadth behind the number |
| **Blocking nobody can see**, respected in every search, match and invitation | Built (item 59) | Platforms block messages; ours removes each from the other's whole marketplace, and the blocked side cannot tell |
| **No cut of any deal** | By design | We never touch the money (constraint 1). How we earn: `docs/REVENUE_RESEARCH.md`, a founder decision |

---

## 6. Novelties next: things nobody has

Version 2's build list is done: rate cards (D-055), fair-rate guidance (D-056), bulk mark-paid with payment references, results from proof (D-070) and matching (Phase D) are built; the disclosure check waits on the validation pack. What comes next is not catching up but **things no competitor reviewed has**. Ranked by what they add to trust, then by cost. **Nothing here is approved.**

| # | Novelty | Why nobody has it | Needs |
|---|---|---|---|
| 1 | **Stated against observed on the Passport**: "says 12,000 average views; median reach read from proof across 9 deals, 10,400" | Needs both a creator's own claims and sealed results from real deals; only we hold both | Results from proof switched on; a decision (it touches the public Passport) |
| 2 | **Camera signatures checked before cleaning**: a proof photo signed by its camera (C2PA Content Credentials) is checked first, and "unedited since capture" is sealed in the record; then the file is cleaned as now | Pixel 10 phones sign every photo; Instagram strips the signatures on upload; our cleaner would strip them too. **Adoption is small today** (Samsung signs only AI-edited images; under 1% of news images carry it), so this is an edge, not a fix | **Waits** (D-071): Pixel holds about 4% of India's ultra-premium segment and our creators use budget Android phones, so almost no proof photo would carry a signature. Revisit when budget phones sign photos |
| 3 | ~~A deal receipt anyone can check~~ | **Declined** (D-071): a deal is private between its two parties | — |
| 4 | **A free quarterly city rate summary**, from anonymous aggregates | We hold published and agreed prices; journalists, agencies and AI search cite it | City figures are built (D-078); the quarterly summary itself is `docs/GO_TO_MARKET.md` section 7 |
| 5 | **Fake-follower signals from observed reach**, not bought data | Observed reach on real deals cannot be bought | Results from proof with real data |
| 6 | **Structured deal notes that join the record**, in place of chat | Chats prove nothing; a note in the record does | A product decision |
| 7 | **Feedback revealed only when both sides have answered**, if feedback is ever added | Removes retaliation, the flaw of two-sided reviews | `docs/PSYCHOLOGY_AND_TRUST.md` section 3 |
| 8 | **A notification budget and quiet hours** | Competitors compete for attention; we respect it | **Built** (D-079) |
| 9 | **Answers inside the phone's assistant**: "has Chennai Bakes paid me?" | Android AppFunctions and iOS App Intents call our API | `docs/PLATFORM_AND_TECH_PLAN.md` A11; Watch |

**What to deliberately not build:** an internet-wide creator database; anything that holds or moves money; exposing contact details; star ratings or reviews in place of the records (opinions can be bought, dated facts cannot); any of the 13 dark patterns India bans (`docs/PSYCHOLOGY_AND_TRUST.md` section 2); an install wall.

---

## 7. The problem we are built on

This still holds, and version 2 adds evidence:

- Payment cycles in Indian influencer marketing typically run **60–90 days**. Nano and micro creators are hit hardest, precisely who we serve.
- Creators who have been burned start **quoting higher prices or demanding deposits**. Brands already pay for late payment, as a risk premium.
- On the other side, **42% of brands** report having paid influencers later found to have heavy fake followings, and nearly two-thirds of Indian Instagram profiles show more than 60% fake followers.
- **Both sides are pricing in each other's risk.** A record of real behaviour lowers that price for everyone who behaves well. That is the commercial argument for this product.
- The market is growing about 25% a year toward **₹3,375–5,000 crore**, and **87% of Indian brands** keep a dedicated creator budget. South India is driving the shift to regional creators.

## 8. The compliance ground is moving

This is recorded for awareness, **not as rules for our product**: constraint 6 says compliance details come from the validation pack, never from research like this. The whole legal map, with what each rule asks of us, is `docs/standards/legal.md`. According to the sources, ASCI updated its influencer guidelines for 2026:

- Disclosure is required for any material connection, including free products and affiliate commissions, not only payment.
- The disclosure is expected near the start of a caption, and within the first seconds of a video.
- AI and virtual influencers have specific rules.
- A platform's own "paid partnership" tag may not be enough on its own.
- Monitoring and penalties are increasing.

Our `disclosure_confirmed` records the creator's statement. Whether that is enough is a validation-pack question.

## 9. What changed in each version

**Version 4 (10 October 2026):** built since version 3, each beating a named competitor:
- invitations and repeat deals (D-084), beating Instagram's, impact.com's and Skeepers';
- one-date availability (D-083), against Passionfroot's slots;
- scam protection inside each feature (items 57 to 60), against Upwork's and Fiverr's moderation;
- breadth behind every record (item 61);
- a UPI pay link that never touches the money (D-085, switched off).

Results from proof moved from proposed to built (switched off). The score is nine closed of fifteen, up from four of eleven.

**Version 3 (1 October 2026):** Meta's Creator Marketing Hub went worldwide on 15 September 2026, still leaving the deal to the two parties; Tamil as the product's language was dropped (D-054); version 2's build list is built, so section 6 is now novelties; section 4 became a plan to close every gap; camera signatures (C2PA) found to be stripped by our own cleaner, which section 6 turns into a novelty.

**Version 2 (21 September 2026):**

| Version 1 said | Version 2 finds |
|---|---|
| "Nobody is serving regional-language creators properly" | **Too strong.** Qoruz and Reelax filter by up to 12 languages, and Social Beat runs Tamil campaigns. The gap is narrower but real: *language as the product's language*, not as a filter |
| 8 competitors | About 20, including **YouTube Creator Partnerships**, **Reelax** (No. 1 in India, June 2026), **Influencer.in** (Chennai), **Wobb**, **JioStarverse**, **Collab**, **Passionfroot** |
| Global platforms cost $795–3,000/month | Indian ones too: ₹25,000 to ₹3 lakh a month, or 8–15% commission |
| Creator delivery record was the top recommendation | **Built** (D-038), and the undated-deal loophole closed (D-039) |

---

## Sources

Version 4:

- [impact.com: joining creator campaigns by invitation](https://help.impact.com/partner/what-would-you-like-to-learn-about/campaigns/creator-campaigns/join-creator-campaigns), [Skeepers: inviting creators](https://help.im.skeepers.com/hc/en-us/articles/19688984132252-How-do-I-invite-creators-to-my-campaign)
- [Upwork: how to identify scams, 2026](https://www.upwork.com/resources/upwork-scams)
- [Passionfroot (TechCrunch)](https://techcrunch.com/2024/10/21/passionfroot-is-building-a-platform-for-brand-and-creator-colloboration-with-a-focus-on-b2b-sector/)

Version 3:

- [Meta enhances Instagram and Facebook tools for creator collaborations](https://www.buzzincontent.com/news/meta-enhances-instagram-and-facebook-tools-for-creator-collaborations-11069426), [Meta Ads updates, September 2026](https://adsuploader.com/blog/meta-ads-updates), [Instagram Creator Marketplace, 2026 (Grynow)](https://www.grynow.in/blog/instagram-creator-marketplace.html)
- [Reelax using AI to fix India's influencer bottlenecks (ANI, August 2026)](https://aninews.in/news/business/reelax-influencer-marketing-platform-is-using-ai-and-automation-to-fix-indias-influencer-marketing-bottlenecks20260817122554/), [Kofluence 2026 report](https://www.adgully.com/post/15568/kofluence-launches-2026-influencer-marketing-report)
- [C2PA adoption in 2026: hardware and verification reality](https://www.softwareseni.com/c2pa-adoption-in-2026-hardware-platforms-and-verification-reality/), [Google Pixel 10 Content Credentials](https://c2paviewer.com/articles/google-c2pa-pixel-10), [Content Credentials on Instagram and other platforms](https://www.lumethic.com/en/articles/content-credentials-social-media-platforms), [Content Credentials (Wikipedia)](https://en.wikipedia.org/wiki/Content_Credentials)

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
