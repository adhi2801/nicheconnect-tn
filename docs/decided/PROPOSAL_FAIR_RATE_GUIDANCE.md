# Proposal: fair-rate guidance

**Status: step 1 approved and built (D-056), 26 September 2026.** Step 2
(section 5) is still a proposal. Written on
`feature/fair-rate-guidance`, which stacks on `feature/rate-card-api` because it
reads the rate card tables (D-055). Backlog item **C3**; #2 on the build list
in `docs/COMPETITIVE_LANDSCAPE.md` section 6.

## 1. What it answers

**A creator** pricing a first Instagram Reel asks: *what do creators like me
charge?* Underpricing is the commonest mistake a new creator makes, and it
teaches brands to expect it.

**A brand** with a budget asks: *is ₹8,000 for a Reel from a 12,000-follower
food creator in Madurai normal?*

One answer serves both: a range (lower quarter, middle, upper quarter) for a
platform, a format and an audience size, narrowed to a niche and a city when
there is enough data, and **always shown with how many creators it came from
and on what date**.

## 2. Where competitors stand (checked 26 September 2026)

| Tool | What it is built from | What it cannot say |
|---|---|---|
| [Collabstr price calculator](https://collabstr.com/influencer-price-calculator) | About 1.1 million packages on its own marketplace, averaged | Worldwide, in dollars, and averages rather than ranges. It says nothing about Tamil Nadu |
| [Qoruz cost checker](https://qoruz.com/tools/influencer-cost-checker) | Costs creators typed into Qoruz, shown **per influencer** | Not a range: it tells a brand one creator's price, not whether it is typical |
| [YouTube desired rates](https://support.google.com/youtube/answer/9385307) | Each creator's own stated rate, in Creator Partnerships | One creator's wish. No comparison at all |

All three work from **asking prices**. None can say what deals actually
closed at. We can, because deal memos record the agreed fee (section 5).
That is where we lead, and it comes in the second step.

## 3. Step 1: asking prices, from published rate cards

**Built from:** `creator_package` rows.

**Grouped by:**
- **platform and format** (always): a YouTube video and an Instagram story are
  not comparable;
- **audience band** (always), from the creator's own follower count on **that
  platform** (`creator_channel.followers`): under 10k · 10k–50k · 50k–100k ·
  100k–500k · 500k and over. Tamil Nadu's pilot creators are mostly micro, so
  the 10k–100k range is split in two;
- **niche and city** (when there is enough data). The answer narrows as far as
  the data allows (niche and city, then niche only, then neither) and says
  which level it used. It never silently widens.

**The arithmetic:**
- Each creator counts **once**: their packages in a group are reduced to their
  own median first, so one creator with five Reel packages cannot outweigh
  four others.
- The figures are the **25th, 50th and 75th percentiles** across creators.
  **No minimum or maximum is ever shown**: each of those is one person's price.
- **Below five creators, no figures**: `null`, meaning *not enough to say*,
  the same rule and wording as the delivery record (D-038). It is never zero
  and never an estimate.
- Audience numbers are self-reported (D-042), so the response says so, and
  gives the date of the **oldest** one behind the figures, because a stale
  count is what a reader needs to know about.

**Worked example.** `GET /api/v1/rate-guidance?platform=instagram&format=reel&followers=12000&niche=food&city=Madurai`

```json
{
  "platform": "instagram",
  "format": "reel",
  "audience_band": "10k_50k",
  "narrowed_to": {"niche": "food", "city": null},
  "source": "published_asking_prices",
  "creators_counted": 9,
  "lower_quarter_paise": 450000,
  "median_paise": 700000,
  "upper_quarter_paise": 1000000,
  "currency": "INR",
  "audience_self_reported": true,
  "audience_figures_from": "2026-09-26",
  "as_of": "2026-09-26"
}
```

Here, food in Madurai alone had fewer than five creators, so the answer used
food across Tamil Nadu and said so (`city: null`).

**Who can read it:** any signed-in creator or brand. Not the open internet,
yet. Rate limited at 60 requests a minute, like every read.

**Cost:** one query with `percentile_cont`, no new table and **no migration**.
It will be measured on seeded data against the 300 ms budget. An index is
proposed only if the measurement asks for one, and that would be its own
migration, needing its own approval.

## 4. Decisions needed

```
DECISION NEEDED 1: Whose prices count
Context:      Brands already see every creator's prices, published or not
              (D-055 point 2). But turning a typed price into a statistic is a
              new *purpose* for it, and under DPDP purpose matters.
              Constraint 6: that is a validation-pack question, not ours to guess.
Option A:     Only creators who have published their rate card
              | + they chose to show their prices to strangers, so counting
                them anonymously needs no new consent
              | − thinner data, especially early | effort S
Option B:     Every creator's packages
              | + about twice the data
              | − rests on a DPDP reading nobody has confirmed | effort S
Recommended:  A now, and ask the validation pack whether B is allowed.
              Widening later is one line; narrowing after publishing figures
              is not possible.
Risk & rollback: A risks "not enough to say" answers for a while. That is
              honest and the pilot is small anyway. Rollback: remove the endpoint.
→ Approve A, B, or modify?
```

```
DECISION NEEDED 2: The minimum sample
Option A:     5 creators | + no single price inferable, useful early
              | − wider ranges | effort S
Option B:     10 creators | + steadier figures | − empty for months at pilot scale
Recommended:  A. The creator count is always shown, so a reader can weigh it.
→ Approve A, B, or modify?
```

The audience bands, the percentiles and the narrowing order follow from the
research above. They are recommendations inside decision 1 and can change
without a migration.

## 5. Step 2, later: agreed fees, which nobody else has

`deal_memo.fee_amount_paise` is what a brand and a creator actually agreed.
It is the better number, and it is ours alone. **It cannot be used yet**,
because `deal_memo.deliverables` is free text. A ₹15,000 memo might be one
Reel or three Reels and a story, so no range per format can be built from it.

Using agreed fees needs, in its own proposal:

1. **Structured deliverables** on the memo, or a link from the memo to the
   package it was agreed from. That is a schema change with its own migration.
2. **A stricter minimum**, of at least five creators *and* three brands, so no
   brand's budget can be worked out.
3. **The validation pack's answer on fee confidentiality.** A fee agreed
   between two parties is more sensitive than a price a creator published
   themselves.

The response already carries `source`, so agreed fees arrive as a second
figure beside the asking prices. The two are never blended: "asked" and
"agreed" mean different things, and the gap between them is itself useful to
a creator.

## 6. What it deliberately does not do

- **Recommend a price.** It shows what others charge. The creator decides.
- **Score a creator** as over- or underpriced to a brand. That would be a
  verdict built from self-reported numbers.
- **Estimate** where data is thin. Five creators or nothing.
- **Touch money.** It describes prices. Nothing is paid through it
  (constraint 1).

## 7. Build plan, once approved

One branch, with the rate card merged first:

1. `app/modules/auth/rate_guidance_service.py`: the query and the narrowing.
   It lives beside the rate card it reads, so there is no new module and no
   architecture decision.
2. Schemas and the router: `GET /api/v1/rate-guidance`.
3. Tests (`testing.md`): the five-creator floor, one creator counted once, no
   minimum or maximum ever in the response, unpublished prices never counted
   (under option A), narrowing reported honestly, 401, 422 for an unknown
   platform or format, and the rate limit.
4. Measured p95 on seeded data, then a decision entry and a report.
