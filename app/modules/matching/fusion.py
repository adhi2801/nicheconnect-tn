"""Hybrid retrieval: meaning and exact words, fused (learned matching step 1, D-167).

An embedding finds a creator whose profile *means* what the brief asks for,
but it can lose an exact word that matters: "Chettinad", a dish, "Tanglish".
Full-text search keeps every exact word, but knows no synonyms. Each misses
what the other finds, so the two rankings are fused.

**Reciprocal rank fusion** (Cormack, Clarke and Büttcher, SIGIR 2009): each
list contributes 1 / (K + rank) for every item it ranks, and the item's score
is the sum. K = 60 is the constant the paper uses. An item absent from a list
contributes nothing from it, so a creator with no embedding yet, or with no
word in common with the brief, is still ranked by the other list.

**The words people wrote, from fields already embedded.** Exact words are
matched between a creator's bio and a brief's title and description: the free
text on each side, a subset of the embedded fields
(`embedding_input.CREATOR_FIELDS`, `CAMPAIGN_FIELDS`), so nothing new enters
matching (constraint 2). City and niche are left out on purpose: the filter
already makes every candidate share them, and in an any-word query they would
drown the brief's distinctive words. Deliverables are left out too: "reels"
says how, not what about. It is computed inside the structural filter, on the
few rows that pass it, so it needs no new column and no index at pilot scale
(docs/PERFORMANCE.md has the timing).

`fuse` states the rule in Python, and the SQL in `rrf_score` computes the same
thing: `tests/modules/matching/test_fusion_properties.py` holds them together.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ColumnElement, Numeric, Text, case, cast, func, literal
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign

RRF_K = 60
# English stemming, so "foods" meets "food" and "cooking" meets "cook". Tamil
# words written in Latin letters pass through it unchanged, which is right:
# they are matched exactly.
CONFIG = "english"
# ts_rank's normalisation 1: divide by 1 + log(document length), so a long bio
# does not outrank a short one for saying more of everything.
LENGTH_NORMALISED = 1
MEANING_DECIMALS = 6


def rrf_scores(rankings: Iterable[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    """Each id's fused score: 1 / (k + rank) summed over the lists that rank it,
    the first place being rank 1."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return scores


def fuse(rankings: Iterable[Sequence[str]], k: int = RRF_K) -> list[str]:
    """Reciprocal rank fusion of ranked lists of ids, best first; ties by id."""
    scores = rrf_scores(rankings, k)
    return sorted(scores, key=lambda item: (-scores[item], item))


def _words(*parts: Any) -> ColumnElement[str]:
    return func.concat_ws(" ", *parts)


def creator_document() -> ColumnElement[Any]:
    """The words a creator wrote about their work: the bio."""
    return func.to_tsvector(
        cast(literal(CONFIG), REGCONFIG), func.coalesce(Creator.bio, "")
    )


def campaign_document() -> ColumnElement[Any]:
    """The words a brand wrote about what it wants: the title and the description."""
    return func.to_tsvector(
        cast(literal(CONFIG), REGCONFIG), _words(Campaign.title, Campaign.description)
    )


def brief_words(campaign: Campaign) -> str:
    """The brief's own words, as `campaign_document` reads them, for a query."""
    return f"{campaign.title} {campaign.description}"


def bio_words(creator: Creator) -> str:
    """The creator's own words, as `creator_document` reads them, for a query."""
    return creator.bio or ""


def any_word_of(text: str) -> ColumnElement[Any]:
    """A query matching any of the text's words: plainto_tsquery joins them with AND,
    which a whole brief would almost never satisfy, so each AND becomes an OR. The
    text arrives as a bound parameter; nothing in it is parsed as query syntax."""
    anded = cast(func.plainto_tsquery(cast(literal(CONFIG), REGCONFIG), text), Text)
    return cast(func.replace(anded, "&", "|"), TSQUERY)


def keyword_rank(
    document: ColumnElement[Any], query: ColumnElement[Any]
) -> ColumnElement[Any]:
    """How well the document matches the query; 0 when it shares no word."""
    return func.ts_rank(document, query, LENGTH_NORMALISED)


def rrf_score(
    distance: ColumnElement[Any] | None, keyword: ColumnElement[Any]
) -> ColumnElement[Any]:
    """The fused score, as a window over the filtered rows: each list ranks only the
    rows it can rank (a vector to compare; a word in common), as `fuse` does.
    `rank()`, not `row_number()`: two rows a list cannot tell apart share a rank, so
    a tie stays a tie for the next rule (newest, past deals) to decide, rather than
    an arbitrary order passing for a preference."""
    terms = []
    if distance is not None:
        # Differences in cosine distance below a millionth are floating-point
        # noise, not meaning: two identical vectors must tie, not rank 1 and 2.
        meaning = func.round(cast(distance, Numeric), MEANING_DECIMALS)
        by_meaning = func.rank().over(order_by=meaning.asc().nulls_last())
        terms.append(case((distance.is_(None), 0.0), else_=1.0 / (RRF_K + by_meaning)))
    by_words = func.rank().over(order_by=keyword.desc())
    terms.append(case((keyword > 0, 1.0 / (RRF_K + by_words)), else_=0.0))
    total: ColumnElement[Any] = terms[0]
    for term in terms[1:]:
        total = total + term
    return total
