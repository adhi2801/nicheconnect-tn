# Proposal: matching that learns from deals that worked

**Status: proposed, 6 November 2026.** Adhi chose this direction the same day ("Learned matching"), from a choice of four. Nothing is built until he approves this proposal (`CLAUDE.md` section 5). It touches matching and embeddings, a schema change and a new dependency, all approval gates.

## 1. What it answers

**A brand** opening its campaign's matches asks: *who here will actually take this, deliver, and be worth it?* Today's answer filters correctly (city, niche, availability, blocks, suspensions) and then orders by past accepted deals and by how close a creator's profile text is to the brief. That order never changes, whatever brands choose. A creator three brands in Madurai picked and paid last month ranks exactly where a creator nobody has picked does, if their text is equally close.

**After this:** the order learns, within the same filter, from what brands did with the matches they were shown and from which deals were completed and paid. Every result still says *why*, in facts.

## 2. Where competitors stand (checked 6 November 2026)

- **YouTube Creator Partnerships** matches with Gemini: strong signals, no reasons shown (`docs/COMPETITIVE_LANDSCAPE.md` section 3).
- **Kofluence, JioStarverse**: "AI matching", undisclosed method, no published evaluation.
- **Ours goes further on two counts**: it learns from **completed, paid deals** (the record nobody else has, D-057, D-085), not from clicks; and it **publishes its evaluation** (section 6), which none of them does.

## 3. What is built, in three steps

**Step 1: hybrid retrieval (no learning, ships first).** Inside today's filter, two rankings are made: the existing embedding similarity (`Qwen3-Embedding-0.6B`, pgvector) and a PostgreSQL full-text ranking over the same public profile text. They are fused by **reciprocal rank fusion**, score = Σ 1 / (60 + rank), the constant from Cormack, Clarke and Büttcher (SIGIR 2009), who showed the fused list beating each input. Exact words ("Chettinad", "Tanglish", a dish) stop being lost to a vector, and synonyms stop being lost to keywords. It needs no data to work.

**Step 2: knowing what was shown.** A new table records each match list a brand saw: campaign, creator, rank, the time, and what the brand did next (opened, invited, accepted an application, nothing). Internal IDs only: no names, numbers or text (constraint 2). Without it, labels are biased by position: what was shown first gets picked more, whatever its quality.

**Step 3: a learned reranker.** A LightGBM **LambdaMART** model reranks the top 100 of step 1, trained nightly as a background job. Each pair's label is graded by what happened, strongest last: 0 shown and passed over; 1 invited or shortlisted; 2 application accepted; 3 deal completed and marked paid. Features, each computed from facts the platform already holds:

| Feature | From |
|---|---|
| Embedding similarity, full-text rank, the fused rank | Step 1 |
| Shared niches; same city | Profiles |
| Follower band against the campaign's budget band | Channels, campaigns |
| Delivery record; typical response time | D-038, D-077 |
| Deals completed with this brand before | Deal memos |
| Booked until; days since last active | D-083, sessions |
| Rank shown at (training only, removed at serving) | Step 2, the position-bias correction |

**Reasons stay factual.** The model's top contributions for a result (LightGBM's per-feature contributions) choose which facts are said first: "completed 4 deals in food, in Madurai, replies within a day". The words are never generated.

## 4. The gate: no model goes live until it is proven better

- **Cold start.** The model stays off until there are at least **2,000 shown pairs with 200 positive outcomes** (**decision**: the numbers). Seeded sample data trains the pipeline and the tests, never a claim of quality.
- **Offline, on a time split** (train on the past, test on the most recent month): NDCG@10 and recall@50 against today's ranking. It ships only if NDCG@10 improves by **at least 5% relative, with a 95% bootstrap interval above zero**, and no group (each city, each niche, creators with no deals yet) does worse by more than 2%.
- **Online**, through gradual rollout (D-160): 10% of brands, then half, comparing invitations accepted per match list shown.
- **Rollback** is a switch: today's ranking is always kept as the fallback, and a missing or failing model falls back to it, in tests.

## 5. Decisions needed

1. **The dependency:** LightGBM 4.7.0 (18 July 2026, MIT licence, Python 3.14 supported). Option A: in the API image for scoring (adds NumPy and SciPy, its size measured before approval). Option B: trained outside the image (in the embedding group) and served through an exported scorer, keeping the image as it is but adding code we own. **Recommended: A**, measured; B if the image grows past the budget set then.
2. **The schema:** `match_impressions` (campaign_id, creator_id, rank, shown_at, outcome, outcome_at), indexed by campaign and creator, kept **180 days** (**decision**; the retention period is the validation pack's to confirm, constraint 6), erased with the account and listed in the export.
3. **The thresholds** in section 4.
4. **Ranking transparency** (`legal.md` section 3.4): the public page that explains, in order, what moves a creator up is updated in the same change as step 3.

## 6. The evaluation, published

A model card, made with the first model as docs/models/MATCHING.md: the data window, the label counts, NDCG@10 and recall@50 against the baseline with their intervals, the per-group results, the features and their importance, known failure cases, and the date. Refreshed with each model that goes live.

## 7. The twelve dimensions

| Dimension | |
|---|---|
| Quality | Step 1 and the gate tested as rules: fusion order by property tests, every feature computed without personal data, the fallback taken when the model is missing; each broken on purpose |
| Novelty | Learns from completed and paid deals, which no competitor has; publishes its evaluation |
| Architecture | `matching` (layer 3); a training job (DBOS, nightly); the model stored with its metrics and version; `ARCHITECTURE_SCALE.md` unchanged |
| Research | Cormack and others, SIGIR 2009 (fusion); LightGBM's LambdaMART objective; NDCG as the ranking measure; sources dated in the build |
| Security | No new route; the impressions table readable only by the job and the export; STRIDE: a forged outcome needs a completed, paid deal, which only both parties make (tampering); no model input from free text a user controls beyond the profile already embedded |
| Privacy and law | IDs only; retention set by the validation pack; in the export and erased with the account; ranking explained publicly (`legal.md` 3.4) |
| Trust and safety | A creator cannot rank higher by getting friends to "accept": labels need a completed and paid deal; a brand's outcomes weigh no more than any other's; new creators guarded by the per-group gate |
| Performance | Reranking 100 candidates in process: budget 15 ms at p95 inside the route's 300 ms, measured |
| Design | No new call: the same match list, the reasons reordered by what mattered |
| Business | Better first matches mean more deals completed per campaign, which is the business; cost: the nightly job's minutes, no paid API |
| Reliability | Model missing, stale or failing: today's ranking, at once; training failing: yesterday's model stays |
| Maintainability | One feature list in one file, its test naming each feature's source; the model card per version; switched off by a setting |

## 8. Build plan, once approved

Step 1, then step 2 (both useful at once), then step 3 behind the gate. Each in its own change, with its tests, decision entry, contract snapshot and documents.
