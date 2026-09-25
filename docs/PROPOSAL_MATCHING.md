# Proposal: Phase D, matching

**Status: proposed. Nothing here is in the code.** Written 23 September 2026.
Needs Adhi's approval (D-051): it adds a dependency, a table, a migration and
an extension, which are four separate gates in `CLAUDE.md` section 5.

## Why this, why now

`app/modules/matching/` is an empty package. Phase D is the only phase with
nothing in it, and `docs/COMPETITIVE_LANDSCAPE.md` builds our whole position
on it: everyone else lets a brand *filter* a creator list, and the claim is
that we *match*. That claim currently has no code behind it.

Everything it needs is in place. pgvector 0.8.6 is pinned and shipping in the
image (D-049), PostgreSQL 18 is running, and `CLAUDE.md` section 3 already
approves the approach in principle: "SentenceTransformers embeddings +
pgvector cosine similarity".

## The shape I recommend, and why it is not "search by vector"

**Filter structurally first, then rank by similarity inside the result, and
always return the reasons.**

A brand does not want the semantically closest creator in Tamil Nadu. It
wants a creator **in a city it ships to, in a relevant niche, inside its
budget, who has actually delivered before** — and among those, the best fit.
City and budget are facts, not vibes, and getting them from a vector would be
both worse and unexplainable.

That ordering has three consequences worth stating:

1. **D3 comes free.** The backlog wants "explainable results: the reasons
   behind every match". If the structured filters do the narrowing, the
   reasons already exist as data — niche overlap, city, budget fit, completed
   deals — and similarity is one more line, not the whole answer.
2. **The candidate set per query is tiny.** A city-and-niche filter over a
   pilot-sized database leaves tens of rows, not thousands.
3. **Which means no vector index at first.** See decision 3.

## Decision 1: which embedding model

| Option | Size | MTEB | Notes |
|---|---|---|---|
| **A. Qwen3-Embedding-0.6B** | 0.6B, 1024 dims | 64.34 | Best score per parameter by a distance. MRL: dimensions can be truncated 32–1024 later without retraining. 100+ languages, `sentence-transformers` compatible |
| B. llama-embed-nemotron-8b | 8B | top of MTEB multilingual at release | Better, and far too heavy for a pilot box |
| C. KaLM-Gemma3-12B | 11.8B | 72.32 | Ceiling model. Not a pilot choice |
| D. potion-base-32M | 32M | 52.13 | Very fast, materially worse |

**Recommended: A.** It is already on the plan's candidate list, it is small
enough to run beside the API, and it is the sweet spot on quality per
parameter.

**It also defuses the Tamil question.** Qwen3 is multilingual, so choosing it
does **not** require settling English-only first. If Tamil comes back, the
same model serves it; if it does not, nothing was wasted. Given that the
Colyv rename and dropping Tamil still have no decision entry, picking a model
that does not depend on that answer is worth real money.

**Effort: M.**

## Decision 2: the dependency, which is the expensive part

**Package:** `sentence-transformers`, which pulls in `torch`.

**Why:** it is the approved approach in `CLAUDE.md` section 3, and it is how
the model is served locally rather than through a paid API.

**Alternatives, including no package:**

- **An embedding API** (Voyage, OpenAI, Cohere). No torch, no model download,
  a per-call cost, and creator profile text leaves our infrastructure. That
  last point needs weighing against constraint 2 even though the text we send
  would carry no PII.
- **ONNX Runtime** instead of torch: much smaller, more work to set up.
- **No package:** Phase D does not happen.

**Security and maintenance impact:** torch will be by a wide margin the
largest dependency in this project, and it lands in `pip-audit`'s scope and
in every CI run and deployment image. **I have not installed it and so cannot
give you a real number.** Before this is approved I would measure the
installed size and the effect on CI time, because it may change the answer:
if the cost is large, the embedding step belongs in a separate worker rather
than inside the API image.

**Effort: S to measure, M to adopt.**

## Decision 3: where the vectors live, and whether to index them

**Recommended:** one new table, not a column on `creator` and `campaign`.

```
creator_embedding      campaign_embedding
  creator_id (PK, FK)    campaign_id (PK, FK)
  embedding vector(1024) embedding vector(1024)
  source_hash text       source_hash text
  model text             model text
  created_at, updated_at created_at, updated_at
```

**Why a separate table:** an embedding is derived data with its own lifecycle.
It is regenerated when the profile text changes or the model changes, it is
throwaway, and it should never be dragged into every `SELECT` on `creator`.
`source_hash` records what was embedded so a rebuild only touches rows whose
input actually changed; `model` means two models can coexist during a
migration.

**Tables affected:** two new. No existing table changes.
**Migration:** one, creating the `vector` extension and both tables. UUIDv7
for the new tables per D-049, since these are the first new tables since.
**Rollback:** drop both tables; drop the extension only if nothing else uses
it. Squawk will check it (D-050).
**Data impact:** none. Nothing existing is read or rewritten, and the tables
start empty.

**No ANN index at first.** pgvector's HNSW is the right index *later*. At
pilot scale, after the structured filter, an exact scan over tens of vectors
is faster than an index lookup and always exactly right. Adding HNSW before
measuring would be the "scale posture" mistake `CLAUDE.md` section 3 warns
about. The trigger to add it: a measured p95 over budget on
`docs/PERFORMANCE.md`'s numbers.

**Effort: M.**

## Decision 4: what text goes in, which is a constraint-2 question

This is D1 in the backlog, and it is the one that can go badly wrong.

**Never embedded:** phone, email, bank or UPI details, the account id, the
exact address. Constraint 2 is absolute, and an embedding is not anonymous —
text can be approximately recovered from a vector.

**Proposed input for a creator:** `city`, `niches`, `languages`, `bio`.
**For a campaign:** `title`, `description`, `niches`, `cities`,
`deliverables`, `campaign_type`.

Both are fields the creator or brand already chose to publish. `display_name`
and `handle` are deliberately left out: a name adds nothing to a match and
pulls a person's identity into the vector.

**The test D1 asks for:** build the input for a creator carrying every PII
field we hold, then assert none of those values appears in the string. It
fails closed — a new PII column added to `creator` breaks the test until
somebody decides where it belongs.

**Effort: S.**

## What I would not do yet

- **No reranker.** A second model for a few dozen candidates is cost without
  a measurable win. Revisit if the match quality is judged poor.
- **No VectorChord, no dedicated vector database.** D-047 already settled
  this: pgvector serves our scale and a broker or a new service needs both
  founders.
- **No automatic re-embedding job.** It needs the job runner, which is still
  undecided. Until then, embeddings are written on create and update, in the
  same transaction as the row.

## The order I would build it

1. The embedding input builder and its PII test (decision 4). No dependency,
   no migration — provable on its own.
2. Measure torch's real cost (decision 2) and bring the number back before
   the dependency is approved.
3. The migration and the two tables (decision 3).
4. Generate embeddings, and the matching endpoint with its reasons.
5. Measure p95 against `docs/PERFORMANCE.md` and only then consider HNSW.

Step 1 is the only one that needs nothing approved beyond this document, and
it is the step that protects constraint 2. I would start there.

→ **Approve which decisions?** 1, 2, 3 and 4 can be answered separately, and
the answer to 2 may reasonably be "measure it first, then ask me again".

## Sources

- [Qwen/Qwen3-Embedding-0.6B — Hugging Face](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Qwen3-Embedding — GitHub](https://github.com/QwenLM/Qwen3-Embedding)
- [Best Open-Source Embedding and Reranker Models 2026](https://builderai.tools/blog/best-open-source-embedding-models-2026)
- [MTEB Leaderboard 2026 — CodeSOTA](https://www.codesota.com/benchmarks/mteb)
- [MTEB — GitHub](https://github.com/embeddings-benchmark/mteb/)
