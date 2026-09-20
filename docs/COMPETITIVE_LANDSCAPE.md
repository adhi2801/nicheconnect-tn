# Competitive landscape

**Researched 21 September 2026.** Sources at the bottom. Every claim here comes
from a source; where something is our judgement rather than a fact, it says so.

---

## 1. The finding that matters most

**Instagram Creator Marketplace went worldwide and stayed free in January 2026.**
It reached India in February 2024, and at the end of January 2026 Meta removed
country restrictions entirely. Brands browse creators by niche, audience
demographics, engagement and location, and invite them to collaborate from
inside Meta Business Suite. It is free to both sides and **Meta takes no cut**.
The January release also added an ad-performance prediction badge and a
similar-creators search.

This has to change how we think about what we are.

**We cannot win on creator discovery.** Meta owns the social graph, has the
engagement data first-hand, charges nothing, and is already inside the app both
sides open every day. Any discovery feature we build is a worse copy of
something free that sits closer to the user.

What Meta's marketplace does **not** do is everything that happens after two
people agree to work together: the terms, the money, the proof, the record of
whether anybody behaved well. That is the whole of our product.

**Position, stated plainly: Instagram is where they meet. We are where the deal
is kept honest.** A brand can find a creator on Instagram for free and still
need somewhere to record what was agreed, what was delivered, whether payment
arrived and what happened when it did not.

---

## 2. The problem we are built on is real, and worse than assumed

This is the strongest validation in the research, and it is not close.

- Payment cycles in Indian influencer marketing typically run **60 to 90 days**.
- Late payment is described as the industry's "most persistent and least
  discussed dysfunction", hitting **nano and micro creators hardest** — which is
  precisely who we serve.
- A creator who posts in March and is paid in June has given an
  **interest-free loan**. For someone with no salary cushion this is called
  "existential", not inconvenient.
- India has **3 million+ creators** working with brands.
- Creators who have been burned start **quoting higher prices or demanding
  deposits** to price in the risk of chasing an invoice.

That last point is the commercial argument for this product in one line: **late
payment is already costing brands money, they just pay it as a risk premium
instead of as a fee.** A brand with a visible record of paying on time should be
able to buy the same work cheaper. Nothing in the market currently lets them
prove it.

### The 2026 trend we deliberately cannot follow

Platforms are responding by **building payment guarantees in** — paying creators
on a fixed cycle whatever the brand does, and absorbing the float themselves.

**We will never do this.** CLAUDE.md constraint 1 is absolute: this service
never receives, pools or holds campaign money. That is not a limitation to work
around, it is the licence, the liability posture and the reason we can operate
without becoming a regulated financial business.

So our answer to the same problem is different, and it is cheaper:
**they use money to fix trust; we use reputation.** A brand's payment record is
visible before a creator agrees to work. Late payment stops being invisible,
which is the only reason it persists. This costs us nothing to run and cannot
put the company's balance sheet behind somebody else's cash-flow problem.

---

## 3. Who else is in the market

### India

| Who | What they are | Their strength | What they are not |
|---|---|---|---|
| **Qoruz** | Discovery + influencer intelligence | The most India-specific full-suite platform; **7M+ Indian creator profiles** | Intelligence for marketers, not a deal-keeping system |
| **Chtrbox** | Established agency-platform since 2016; **listed on BSE SME in late 2025** | Data-led, enterprise scale, real credibility | Enterprise-priced; a Tamil Nadu sweet shop is not the customer |
| **One Impression** | Creator collaboration and campaign execution | Cross-platform campaign management | Brand-side tooling |
| **Winkl** | Curated micro/nano marketplace | Closest to us on **creator size and localised outreach** | Campaign tooling, not payment accountability |
| **Kofluence** | AI-driven matching, marketplace model | Fast, affordable, **aimed at small and mid-sized brands** | Discovery and matching; no payment record |

### Global

| Who | Model | Price |
|---|---|---|
| **Collabstr** | Open marketplace, book creators directly, transparent pricing | **Commission per booking**, no subscription |
| **Aspire** | Long-term creator relationships | **~$1,000–3,000+/month** |
| **Upfluence** | Enterprise discovery | **$795+/month** |

**The pricing observation that matters:** at $795–$3,000 a month, none of these
are reachable by the business we are building for. A Coimbatore bakery running
three campaigns a year cannot justify a monthly SaaS fee larger than the
campaign budget. Collabstr's commission model is the only one that scales down —
and it takes a cut of the money, which we have chosen not to touch.

**Our pricing gap is therefore a real position, not an accident:** no
subscription, no commission, because we never handle the money.

---

## 4. What they have that we do not

Honest list. These are real gaps, not dismissals.

| Feature | Who has it | Should we? |
|---|---|---|
| **Creator discovery with audience analytics** | Qoruz (7M profiles), all majors | **No.** Meta does it free and better. Our matching (Phase 5) should match *campaigns to creators already on our platform*, not crawl the internet |
| **Fake-follower / authenticity checks** | Winkl, Qoruz | **Eventually.** Needs third-party data. High value, high cost |
| **Campaign performance tracking** (reach, engagement, ROI) | All majors | **Yes, minimally.** We already hold proof links; reading public engagement counts closes the loop from deal to result |
| **AI creator matching** | Kofluence | **Yes — Phase 5, already planned** |
| **Transparent creator rate cards** | Collabstr | **Yes.** Cheap to build, removes the most awkward conversation in every deal |
| **Multi-platform creator profiles** (YouTube, etc.) | One Impression, most | **Yes.** We are Instagram-shaped today and Tamil Nadu creators are on YouTube heavily |
| **Contracts / e-signature** | Enterprise platforms | **Partly done.** Our deal memo is a lighter version; acceptance is recorded |
| **Invoicing, GST, TDS** | Agency platforms | **Blocked** — validation pack, never invent (constraint 6) |

## 5. What we have that they do not

| Ours | Status | Why it is a moat |
|---|---|---|
| **Brand payment reliability record** | **Built** | Nobody publishes whether a brand actually pays. It is the single most valuable fact a creator wants and nobody will tell them |
| **Payment record without holding money** | **Built** | Competitors either take a cut or ignore payment. We do neither |
| **Neutral dispute timeline, exportable** | **Built** | Platforms either judge disputes or have none. Ours is a dated record either side can take elsewhere |
| **Deal memo with auto-approval clock** | **Built** | Stops "we'll review it next week" running forever |
| **Public Creator Passport, consent-based** | **Built** | A portable, opt-in profile that works as a link in a bio |
| **Tamil-first** | Planned | Every platform above is English-first. **Nobody is serving regional-language creators properly** |
| **No subscription, no commission** | By design | Structurally cheaper than anyone at our end of the market |

---

## 6. The gap in our own product nobody has pointed out

We built a **brand** reliability record. We did not build the mirror.

A brand deciding between two creators has exactly the same problem a creator
has: did this person deliver, on time, with the disclosure they promised? We
hold every fact needed — proof submitted on time or late, revisions requested,
`disclosure_confirmed`, memos cancelled after work began (D-026 already
distinguishes `withdrawn_early` from a real cancellation), content taken down
early (`content_removed_on`).

**A creator delivery record is the highest-value thing we could build next**,
and it is the natural pair to what already exists. It also protects creators as
a group: today a brand burned once has no way to tell a reliable creator from an
unreliable one, so it prices every creator as risky — the mirror image of the
payment problem.

It must be built to the same rules as the brand record (D-034): silence cannot
launder it, "new" cannot be a hiding place, and nothing is smoothed.

---

## 7. What would make this look like it came from a company with real money

Ordered by value, not by effort.

1. **Creator delivery record** — the missing mirror. Nobody else has either half.
2. **Rate cards on the Creator Passport** — Collabstr proves transparent pricing works; it also makes the Passport link more useful to a creator.
3. **Multi-platform profiles** — YouTube especially. We are Instagram-shaped and Tamil Nadu is not.
4. **Campaign results from proof links** — closes deal → delivery → payment → *result*. No competitor closes the whole loop because none of them hold all four.
5. **Matching (Phase 5)** — but as *campaign ↔ creator fit within our own marketplace*, not internet-wide discovery we would lose.
6. **Tamil throughout** — the only structural advantage here that money cannot quickly copy.
7. **Authenticity signals** — later; needs third-party data.

**What to deliberately not build:** internet-wide creator discovery, audience
demographic crawling, anything that holds money.

---

## Sources

- [Instagram Creator Marketplace — brand guide, 2026](https://www.storika.ai/guides/instagram-creator-marketplace)
- [Instagram expands Creator Marketplace geography](https://www.socialmediatoday.com/news/instagram-expands-geographic-creator-marketplace/715865/)
- [India's creator economy: broken payments as the bottleneck](https://www.thereelstars.com/tech/indias-creator-economy-is-booming-but-broken-payments-are-becoming-its-biggest-bottleneck/)
- [Creator payment SLAs: fixing late pay](https://www.influencers-time.com/creator-payment-slas-fixing-late-pay-before-it-costs-you/)
- [Top influencer marketing platforms in India, 2026](https://www.adgully.com/post/17224/top-10-influencer-marketing-platforms-in-india-2026)
- [India's top influencer marketing platforms](https://starbuzz.ai/blog/213-indias-top-10-influencer-marketing-platforms-you-need-to-know)
- [Collabstr vs Aspire vs CreatorIQ, 2026](https://collabstr.com/blog/collabstr-vs-aspire-vs-creatoriq)
- [Influencer platform cost comparison](https://collabstr.com/blog/influencer-marketing-platforms-cost-comparison-upfluence-alternatives)
