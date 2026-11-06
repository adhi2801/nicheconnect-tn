# Proposal: a fair price for this creator, with honest uncertainty

**Status: approved as written, 6 November 2026 (D-167).** It extends fair-rate guidance step 1 (D-056, `docs/decided/PROPOSAL_FAIR_RATE_GUIDANCE.md`), shares learned matching's dependency, and changes a public contract additively.

## 1. What it answers

Fair-rate guidance today answers for a **group**: "creators with 10,000 to 50,000 followers charge ₹3,000 to ₹6,000 for a Reel" (the quartiles, five creators or nothing). It cannot answer for **this** creator, whose engagement, niche and city put them somewhere inside or outside that band.

**After this:** "Creators like you charge **₹4,200 to ₹6,800** for a Reel. Nine in ten similar published prices fall in a range like this. Based on 312 rate cards." The range is personal, and the "nine in ten" is a guarantee the method gives, checked on held-out data and published, never a slogan.

## 2. Where competitors stand (checked 6 November 2026)

- **Collabstr's calculator, Qoruz's cost checker, YouTube's Desired Rates**: a point estimate or a creator's own wish, with no stated uncertainty and no sample size (`docs/COMPETITIVE_LANDSCAPE.md` section 4).
- **Ours goes further**: a range with a measured coverage, the number of rate cards behind it, and a refusal to answer when the data is thin.

## 3. The method

- **Quantile regression** (LightGBM's quantile objective, the same dependency as learned matching) predicts the 5th and 95th percentile of the published price from: platform, format, follower count, engagement where the platform supplies it (items 29 to 31), niche and city.
- **Conformalized quantile regression** (Romano, Patterson and Candès, NeurIPS 2019) then widens or narrows those bounds using a held-out calibration set, so that **at least 90% of new prices fall inside**, whatever the model's errors, while staying "fully adaptive" to how prices spread. The paper gives the guarantee; our test set checks it.
- **Only published rate cards**, each creator counted once, as step 1 (D-056): the consent reasoning there is kept unchanged.

## 4. When it answers, and when it says "not enough"

- The model is trained only when there are at least **200 creators' published cards** for a platform (**decision**); below that, step 1's quartiles answer, as today.
- A range is shown only when at least **5 creators** in the calibration set are similar (same platform, format and follower band), or the answer falls back to step 1, saying so.
- **Never a single price.** Never a verdict on a quote.

## 5. The contract, additively

`GET /api/v1/rate-guidance` gains an optional `interval`: `{low_paise, high_paise, coverage: 0.9, method: "conformal" | "quartiles", based_on}`. Every field it answers today stays exactly as it is.

## 6. The evaluation, published

A model card, made with the first model as docs/models/RATE_INTERVALS.md: the empirical coverage on a held-out set (target 90%, shown with its confidence interval), the median interval width against step 1's quartile width, the pinball loss, coverage per follower band and city (no group below 85%), the data window and its size.

## 7. Decisions needed

1. **The dependency**: LightGBM 4.7.0, shared with learned matching (one approval covers both).
2. **The thresholds**: 200 cards to train, 5 similar creators to answer, 90% coverage.
3. **No migration**: the model and its calibration scores are stored with the matching model's registry (learned matching, section 5), or as files in S3 if that proposal is not approved.

## 8. The twelve dimensions

| Dimension | |
|---|---|
| Quality | Coverage tested as a property on generated data where the truth is known; the fallback to quartiles and the refusal to answer each broken on purpose |
| Novelty | A personal range with a published, guaranteed coverage; no competitor states its uncertainty |
| Architecture | `insights` (layer 3), beside step 1; training in the nightly job; `ARCHITECTURE_SCALE.md` unchanged |
| Research | Romano, Patterson and Candès (NeurIPS 2019); LightGBM's quantile objective; sources dated in the build |
| Security | The same route, the same access (any signed-in creator or brand); STRIDE: inference of one creator's price prevented by the 5-similar floor (information disclosure) |
| Privacy and law | Published cards only, as D-056; nothing new collected; one creator's price never recoverable from an answer |
| Trust and safety | A creator cannot move a range by publishing an absurd price: each creator counts once, and calibration is robust to one outlier among 200 |
| Performance | One model prediction per request, under 5 ms; the route's 300 ms budget kept, measured |
| Design | The same screen, one line richer: the range, "nine in ten", the count |
| Business | Creators price with confidence and brands judge quotes fairly, so fewer deals stall on price; cost: minutes of nightly training |
| Reliability | Model missing or below threshold: step 1's quartiles, at once |
| Maintainability | One training function, its model card per version, switched off by a setting |

## 9. Build plan, once approved

The training job and evaluation first, run on seeded data to prove the pipeline (never a quality claim); the contract field and screen line once a platform passes 200 real cards.
