# A campaign brief from a few sentences (item 40, D-156)

**Status: Approved by Adhi on 4 November 2026 (D-156); built the same day on `feature/brief-drafts`, switched off until the validation pack answers. Not reviewed by Erode Harish (D-051).** Kept as the reasoning behind the build.

## What it does

A brand writes a few sentences: the product, who it is for, what it wants made, any budget or city. Within about a minute it has a draft of the campaign's title, description, deliverables, type, niches, cities and budget, filled only where its words support it, to prefill the new-campaign form, edit and publish. The draft creates nothing.

## The twelve dimensions (D-098, D-139)

| Dimension | |
|---|---|
| Quality | API tests through the job with a fake drafter (no test calls the API); the drafter's request and answer handling with a fake client; twelve rules broken on purpose, each caught (one first survived: a guard covered by another, so each got its own test) |
| Novelty | AI brief writers elsewhere draft freely from a prompt. Ours fills only what the brand's words support, never invents a budget or a city, checks every field against a campaign's own limits, and never asks a creator to pay. Competitors' versions were not re-checked for this file |
| Architecture | `campaigns` (layer 4): `brief_drafter` (the seam), `brief_service`, `brief_jobs`, `brief_router`. A job on DBOS like the proof reader; no new deployable. `ARCHITECTURE_SCALE.md` unchanged |
| Research | Claude API structured outputs (`messages.parse` with `output_format`), effort, server-side refusal fallbacks: the claude-api skill's documentation, read 4 November 2026, checked against the installed SDK 2.3.0 |
| Security | Spoofing: a brand account through the one access check. Tampering: drafts are the brand's, read through `brand_id`. Repudiation: who asked is kept. Disclosure: a draft is read only by the brand's team, 404 otherwise, and the stranger walk covers it. Denial of service: 5 a minute and 30 a day per account, three waiting per brand, a daily ceiling on drafts. Elevation: only the roles that run campaigns may ask (`brand_acts`). Prompt injection: the brand's words are content, the answer a fixed shape, every field checked |
| Privacy & law | A brand's description of its own campaign, sent to Anthropic: legal.md section 3.1, a Confirm item (processing outside India), so built switched off. Kept a week; in the asker's export; erased with the brand |
| Trust & safety | The model is told never to ask creators to pay; a brand still publishes through the usual checks, which flag fee requests and contact details (`text_flags`) |
| Performance | The request writes one row and calls nothing outside. The job drafts at most 10 a minute. The routes' p95 is measured when it is switched on with real traffic; today each is a couple of short queries |
| Design | Ask, then read the `Location` until ready: two calls, then the existing create-campaign form |
| Business | Fewer abandoned campaigns. Cost: roughly 1,500 input and 500 output tokens a draft on Claude Opus 5.5 ($4 and $20 a million tokens), under a rupee each; the daily ceiling caps it |
| Reliability | The SDK retries 429s and 5xx; a failed call is tried three times by the job, a refusal or an out-of-shape answer is final; a crash mid-draft leaves it waiting for the next run; the advisory lock stops two runs drafting one |
| Maintainability | Additive routes; the prompt has a version; the model is a setting |
