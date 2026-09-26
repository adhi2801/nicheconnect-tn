"""Turning text into a vector, and nothing else (D-052).

Kept deliberately thin and free of database code so the expensive part — a
1.2 GB model and a torch import — sits behind one seam that tests can replace.

**The model is loaded lazily, once.** Importing this module must stay cheap:
`app.main` imports the whole module tree at start-up, and a model load there
would add seconds to every boot, every test run and every CI job, for a
feature most requests never touch.

**Nothing here decides what to embed.** `embedding_input.py` does, and it is
where constraint 2 is enforced. This module would happily embed a phone
number; the reason it never sees one is that the other module refuses to
declare it.

**Not on the request path.** `CLAUDE.md` section 3 says an external call never
blocks a request. Callers embed on write, or in a batch, never inside a read
a person is waiting on.

Measured on this laptop, CPU-only torch 2.14.0, 23 September 2026 — these are
the numbers the two rules above rest on:

    model load, once per process     23.6 s
    one embedding, model warm       ~220 ms
    batch of 32, per item           ~205 ms
    30 real creator profiles         18.6 s  (~620 ms each; real bios are
                                              longer than a test string)
    the same 30, nothing changed      0.01 s (every row skipped on source_hash)

So: the load alone would add 23 seconds to every boot, every test run and
every CI job if it happened at import. And a single embedding is already over
the 500 ms write budget in `docs/standards/backend.md` section 6 before any
database work — which is why nothing here may ever sit inside a request.

The last line is the whole point of `source_hash`: 18.6 s becomes 0.01 s when
the text has not changed.
"""

import hashlib
import threading
from typing import Any, Protocol, cast

# The model chosen in D-052. Its native width is 1024, which is what the
# column is declared as, so a change here needs a migration.
MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_DIMENSIONS = 1024


class WrongDimensions(RuntimeError):
    """The model returned a vector the column cannot store."""


class Encoder(Protocol):
    """What this module needs from a model, so a test can pass a fake."""

    def encode(self, sentences: list[str], **kwargs: Any) -> Any: ...


_model: Encoder | None = None
_lock = threading.Lock()


def load_model() -> Encoder:
    """The model, loaded once per process.

    Imported inside the function on purpose: `sentence_transformers` pulls in
    torch, and that import alone is the slowest thing in the project. Keeping
    it here means a process that never embeds never pays for it.
    """
    global _model
    if _model is None:
        with _lock:
            if _model is None:  # another thread may have won the race
                from sentence_transformers import SentenceTransformer

                # SentenceTransformer satisfies Encoder structurally; mypy
                # cannot see that through the local import.
                _model = cast(Encoder, SentenceTransformer(MODEL_NAME))
    loaded = _model
    if loaded is None:  # pragma: no cover - the lock above guarantees it
        raise RuntimeError("the model failed to load")
    return loaded


def set_model(model: Encoder | None) -> None:
    """Replace the model, for tests. `None` restores lazy loading."""
    global _model
    _model = model


def source_hash(text: str) -> str:
    """What the stored `source_hash` column holds.

    A rebuild compares this and re-embeds only rows whose input really
    changed, which matters because embedding is the slow part. It is not a
    security boundary: it identifies text, it does not hide it.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed(texts: list[str]) -> list[list[float]]:
    """Embed each text, in order, as a list of floats.

    Batched because a model encodes many texts far faster than one at a time,
    and callers rebuilding a table always have many.
    """
    if not texts:
        return []

    vectors = load_model().encode(texts, normalize_embeddings=True)
    result = [[float(value) for value in vector] for vector in vectors]

    for vector in result:
        if len(vector) != EXPECTED_DIMENSIONS:
            raise WrongDimensions(
                f"{MODEL_NAME} returned {len(vector)} dimensions, "
                f"but the column stores {EXPECTED_DIMENSIONS}. A model change "
                f"needs a migration, not a config change."
            )
    return result


def embed_one(text: str) -> list[float]:
    """One text, for the single-row case."""
    return embed([text])[0]
