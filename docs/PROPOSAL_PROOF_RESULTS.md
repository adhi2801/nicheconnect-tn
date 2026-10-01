# Proposal: results a brand can trust, read from the proof (competitive #4)

**Status: approved 1 October 2026 (D-070); steps 1 to 6 built the same day on `feature/proof-results`. Off by a setting until the validation pack answers (section 6); the model is chosen once the test set exists (step 2).**

## 1. Why

A brand pays for reach, and today it gets a screenshot. Indian brand guides
now name the trick: **"the Screenshot Portfolio Scam"**, edited insight
screenshots with inflated reach. Their advice is to ask for screenshots
"directly from the creator's phone, not a PDF or shared file that can be
edited", which a brand cannot check either.

The real numbers sit inside Instagram and YouTube. Instagram's API returns a
post's reach only when **the creator connects their own account** to an
approved app (one connection per creator, after Meta's app review). So
platforms with money buy data deals and connections; a small Tamil Nadu brand
gets the screenshot.

**What we already hold, since today:** the proof files (D-065), cleaned of
location data, with each file's fingerprint sealed in the deal record
(D-057, D-066). **What nobody holds end to end:** deal, delivery, payment
*and result* in one record (`COMPETITIVE_LANDSCAPE.md` section 6, #4).

## 2. What it does

Four layers, each honest about what it proves:

| Layer | What happens | What the brand sees |
|---|---|---|
| **1. Read** | After a proof screenshot is cleaned, a background job asks Claude to read the numbers on it: platform, account handle, post date, views, reach, likes, comments, saves, shares, whichever appear. Structured output, never free text | The numbers, labelled **"read from the creator's screenshot"** |
| **2. Checked** | Plain rules we compute, no AI: the handle matches the creator's linked channel; the post date falls inside the deal; the numbers agree with each other (likes never above views, reach never above impressions); reach against the creator's **own stated** followers and average views (`creator_channel`, D-055) | Each check passed, or a plain flag: *"reach is 9× this creator's stated average"*. A flag says **unusual**, never **fake** |
| **3. Sealed** | The reading and the checks are sealed in the deal record next to the screenshot's fingerprint, as a new entry kind | Numbers nobody can quietly change later, the creator or us |
| **4. Verified** (later step) | When the creator connects Instagram or YouTube, or tags the brand as paying partner, the platform's own numbers replace the reading | **"Verified by Instagram"** |

The creator sees the same reading and can mark a misread. The mark is kept
next to the reading, never instead of it.

**What it deliberately does not claim.** An AI cannot reliably tell a skilled
edit from a real screenshot, so a screenshot reading is never called
"verified". The value is in the other three things: numbers in one place and
one format, checks against facts we already hold, and a seal. Layer 4 is the
only "verified".

**Then, the novelty no competitor has:** across deals, the Creator Passport
can show **stated against observed**: "says 12,000 average views; across 9
deals, median reach read from proof 10,400". Collabstr has star reviews,
which are opinions; Instagram has stats but no deals. This is a delivery
record with results in it. (A later decision; it touches the public Passport.)

## 3. How it compares

| Who | Results | Trust in them |
|---|---|---|
| Collabstr | One-click post analytics | Through platform connection |
| Wobb | Sales-tracking pixel | Sales only |
| Influencer.in, JioStarverse, Qoruz | Full reporting, agency-run | Data deals, enterprise budgets |
| Instagram Creator Marketplace | Partnership ad metrics | Only for partnership ads, and the deal is "handled separately" |
| **Us** | Every proof, any size of brand | Read, checked against the creator's own claims, sealed; verified where connected |

## 4. Limits for the pilot

- **Images only**, the ones already on proof (D-065: JPEG, PNG, WebP, 10 per proof).
- **Instagram and YouTube insights screens** in English; anything else is
  read as "no numbers found", never guessed.
- **Only the clean copy** is ever sent, never an original (no location data).
- Off by a setting until the privacy question in section 6 is answered.

## 5. Decisions needed

```
DECISION NEEDED 1: Build results from proof (layers 1 to 3 now, layer 4 later)
Context:  Proof files exist since today; brands get screenshots they cannot
          trust, and the real numbers need a creator's own platform login.
Option A: Read, check and seal every proof screenshot, in a background job
          | + results for every deal, any brand; checks against facts we
          hold; a seal nobody else has | − an AI provider receives proof
          screenshots (section 6); a cost per image (section 7) | effort M
Option B: Wait for layer 4 only (platform connections)
          | + platform-verified numbers | − needs Meta app review and business
          verification (the same wait as WhatsApp, E1); most small creators
          will not connect; months away | effort L, blocked
Option C: Brands type the numbers in themselves | + no AI | − no check,
          no seal, nothing a brand cannot already do in a spreadsheet | effort S
Recommended: A now, B as layer 4 when Meta verification exists.
Risk & rollback: a misread number. Every reading is labelled, the creator can
          mark it, and the screenshot stays one tap away. Rollback: the
          setting off; readings already sealed stay, labelled.
```

```
DECISION NEEDED 2: Which Claude model reads the screenshots
Context:  The cost per image scales with the model (section 7). Reading
          numbers off a clean screenshot is extraction, not reasoning.
Option A: Claude Opus 5.5 (the current default) | + the most accurate
          | − the highest cost, about ₹2–3.5 an image (estimate)
Option B: Claude Sonnet 5.5 | + about half the cost
Option C: Claude Haiku 4.5 | + about a quarter of the cost | − the oldest
Recommended: decide on measurement, not guesswork: step 2 below builds a test
          set of real insights screenshots (yours and Harish's own accounts,
          with the true numbers written down) and runs all three. The cheapest
          model that reads every number right on that set wins. Until then,
          Opus 5.5.
Also:     the job is not urgent, so the Batch API halves any model's price,
          at the cost of numbers appearing within hours instead of a minute.
```

```
DEPENDENCY REQUEST
Package:     anthropic 1.11.0 (runtime)
Why:         Claude's official Python library: image input, structured
             output, retries with backoff built in (CLAUDE.md section 3)
Alternatives: raw HTTP calls (security and retry code we should not write);
             another AI provider (no reason found to prefer one; the test set
             in decision 2 would show it); no package (option C)
Security/maintenance: maintained by Anthropic; needs httpx2 2.x, which we
             already pin (2.13.0, D-047), so no conflict; pip-audit and Grype
             cover it like every package
```

```
SCHEMA REQUEST
Tables affected: new table `proof_file_reading`: one row per cleaned proof
             file read: the file, the model and prompt version, status (read,
             no numbers found, failed), the numbers (nullable integers, each
             named), platform, handle and post date as read, each check's
             result, the creator's misread mark, times. The deal record gets
             one new entry kind, `proof_results_read`, sealing the reading's
             digest beside the file's fingerprint.
Migration:   one migration; the record's kind check widened NOT VALID then
             validated (the D-066 pattern)
Rollback:    downgrade drops the table; it refuses while any sealed
             `proof_results_read` entry exists (the record is append-only)
Data impact: none on existing rows
```

**Also needed (infrastructure, same approval):** the Anthropic API key as a
secret in Secrets Manager, read by the app's task only; never in settings or
code. Not applied until AWS exists.

## 6. Privacy: a question for the validation pack

- An insights screenshot shows the creator's handle and their audience's
  **aggregate** figures (cities, age bands, gender split). No personal data
  of any one person, but it is the creator's business data.
- Sending it to Anthropic makes Anthropic a processor of it. **Whether DPDP
  needs the creator's explicit consent for that, and what the processor
  terms must say, is a validation pack question** (constraint 6). We do not
  guess it.
- Until it is answered: built and tested, **off by a setting** in every real
  environment. The proposal is for a default of asking the creator once,
  in plain words, before their first screenshot is read; that wording too
  comes from the validation pack.
- Readings never enter matching or embeddings (constraint 2).

## 7. Cost

Estimates, corrected on 1 October 2026 against Anthropic's vision
documentation, to be replaced by measured numbers in step 2:

- An image costs one token per 28×28 pixel square. Opus 5.5 reads images up
  to 2,576 pixels on the long side at full sharpness, so a 1080×2400 phone
  screenshot is about **3,400 image tokens**, plus about 600 of instructions:
  about 4,000 in. Output, with the model's thinking at low effort, about 300 to
  1,000 tokens.
- **Opus 5.5** ($4 in, $20 out per million tokens): about $0.016 in plus
  $0.006 to $0.020 out, **$0.02 to $0.04, ₹2 to ₹3.5 an image** (at ₹88 to the
  dollar).
- **Haiku 4.5** reads at most 1,568 pixels on the long side, so the same
  screenshot is about 1,500 image tokens at a quarter of the price per token:
  well under ₹0.5 an image. Smaller text may be harder to read at that size,
  which is exactly what the test set measures. Sonnet 5.5 sits between.
- **Batch API**: half of any of these, with numbers appearing within hours.
- 1,000 proofs of 3 screenshots a month: about ₹6,000 to ₹10,000 on Opus 5.5,
  about ₹1,000 or less on Haiku 4.5, before batching.
- A daily spend ceiling in settings stops the job, never a request, if
  something loops.

## 8. Build order, once approved

Each step is one commit with its tests:

1. The reader seam (like the embedder's): Claude in production, a fake in
   tests. No test in CI ever calls the API.
2. **The test set**: real insights screenshots from our own accounts with the
   true numbers written down; a script that scores each model on it and prints
   the cost. This decides decision 2.
3. The `proof_file_reading` table and migration.
4. The job: read each cleaned file, run the checks, seal, after cleaning;
   off by default.
5. The readings on the proof endpoints, for both sides, and the creator's
   misread mark.
6. Infrastructure: the API key secret and its permission.

Later and separate: stated against observed on the Passport; layer 4,
platform-verified numbers.

## Sources

- [Fake followers in India: the Screenshot Portfolio Scam (2026)](https://gmtalentsnetwork.com/fake-followers-in-india/)
- [How to check influencer authenticity in India: vetting checklist](https://www.groovenexus.com/brands/brands-influencer-marketing-how-to-check-influencer-authenticity-india/)
- [Instagram API integration 2026: creator authentication required for insights (Phyllo)](https://www.getphyllo.com/post/instagram-api-integration-101-for-developers-of-the-creator-economy)
- [Instagram API changes in 2026](https://storrito.com/resources/instagram-api-2026/)
- [Instagram Branded Content API explained, June 2026](https://creatorlanehq.com/blog/instagram-branded-content-api-explained): reports that a brand tagged as paying partner can read views and reach of the tagged post through the API. A blog, not Meta's documentation: **to confirm with Meta before layer 4 is designed**
- [Influencer campaign reporting tools, 2026](https://iqfluence.io/public/blog/influencer-campaign-reporting-tools)
- Claude models and prices: Anthropic's published table, as of 25 September 2026; `anthropic` 1.11.0 and its `httpx2` requirement from PyPI, 1 October 2026
