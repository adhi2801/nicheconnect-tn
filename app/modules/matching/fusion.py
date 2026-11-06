"""Hybrid retrieval: meaning and exact words, fused (learned matching step 1, D-167).

An embedding finds a creator whose profile *means* what the brief asks for,
but it can lose an exact word that matters: "Chettinad", a dish, "Tanglish".
Matching words keeps every exact word, but knows no synonyms. Each misses
what the other finds, so the two rankings are fused.

**Reciprocal rank fusion** (Cormack, Clarke and Büttcher, SIGIR 2009): each
list contributes 1 / (K + rank) for every item it ranks, and the item's score
is the sum. K = 60 is the constant the paper uses. An item absent from a list
contributes nothing from it, so a creator with no embedding yet, or with no
word in common with the brief, is still ranked by the other list. Items a list
cannot tell apart share its rank, and the next item's rank counts everyone
ahead of it (competition ranking, SQL's `rank()`), so a tie stays a tie.

**The words people wrote, from fields already embedded.** Exact words are
matched between a creator's bio and a brief's title and description: the free
text on each side, a subset of the embedded fields
(`embedding_input.CREATOR_FIELDS`, `CAMPAIGN_FIELDS`), so nothing new enters
matching (constraint 2). City and niche are left out on purpose: the filter
already makes every candidate share them, and in an any-word match they would
drown the brief's distinctive words. Deliverables are left out too: "reels"
says how, not what about. Each row's words are stored with it, computed by
the database whenever the text changes (`creator.bio_words`,
`campaign.brief_words`, D-173), so a request reads them rather than cutting
up to 4,120 characters a row into words (docs/PERFORMANCE.md has the timing).

**Which words, counted how.** Both texts are cut into distinct stemmed words
by PostgreSQL's English parser, and the score is the words they share divided
by the square root of how many distinct words the document holds: the cosine
of the two word sets (Salton and McGill, 1983), less a factor the same for
every row. Saying a word twice adds nothing, and a long list of every word in
the niche must share many more of the brief's words than a short honest bio
to pass it. No text is ever parsed as query syntax.

`fuse` states the rule in Python, and the SQL in `rrf_score` computes the same
thing: `tests/modules/matching/test_hybrid_retrieval_api.py` holds them
together, ties included.
"""

from collections.abc import Iterable, Mapping
from fractions import Fraction
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Float,
    Numeric,
    Text,
    any_,
    case,
    cast,
    func,
    literal,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, REGCONFIG

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign

RRF_K = 60
# English stemming, so "foods" meets "food" and "cooking" meets "cook". Tamil
# words written in Latin letters pass through it unchanged, which is right:
# they are matched exactly.
CONFIG = "english"
# Distances are compared after rounding to six decimals, so two identical
# vectors whose float arithmetic differs in the last bits tie rather than rank
# 1 and 2. Rounding, not a tolerance: two distances either side of a rounding
# boundary still differ, by a millionth at most.
MEANING_DECIMALS = 6


def competition_ranks(scores: Mapping[str, float], *, best_first: bool) -> dict[str, int]:
    """Each id's rank among the scores: 1 plus how many score strictly better, so
    equal scores share a rank and the next one counts everyone ahead (SQL's
    `rank()`)."""
    ordered = sorted(scores.values(), reverse=best_first)
    ranks: dict[str, int] = {}
    for item, score in scores.items():
        ranks[item] = 1 + sum(
            1 for other in ordered if (other > score if best_first else other < score)
        )
    return ranks


def rrf_scores(rankings: Iterable[Mapping[str, int]], k: int = RRF_K) -> dict[str, float]:
    """Each id's fused score: 1 / (k + rank) summed over the rankings that rank it,
    the first place being rank 1."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for item, rank in ranking.items():
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def fuse_ranks(rankings: Iterable[Mapping[str, int]], k: int = RRF_K) -> list[str]:
    """Reciprocal rank fusion of rankings that may hold ties, best first; ties by id.
    Summed exactly: in floating point, equal sums added in a different order can
    differ in the last bit, and the order of the lists would then decide a tie."""
    scores: dict[str, Fraction] = {}
    for ranking in rankings:
        for item, rank in ranking.items():
            scores[item] = scores.get(item, Fraction(0)) + Fraction(1, k + rank)
    return sorted(scores, key=lambda item: (-scores[item], item))


def fuse(rankings: Iterable[Iterable[str]], k: int = RRF_K) -> list[str]:
    """Reciprocal rank fusion of ranked lists of ids with no ties, best first."""
    return fuse_ranks(
        (
            {item: rank for rank, item in enumerate(ranking, start=1)}
            for ranking in rankings
        ),
        k,
    )


def _config() -> ColumnElement[Any]:
    return cast(literal(CONFIG), REGCONFIG)


def _words(document: ColumnElement[Any]) -> ColumnElement[Any]:
    return func.tsvector_to_array(document)


def creator_document() -> ColumnElement[Any]:
    """The words a creator wrote about their work: the bio's, stored with the row."""
    return Creator.bio_words


def campaign_document() -> ColumnElement[Any]:
    """The words a brand wrote about what it wants: the title's and the
    description's, stored with the row."""
    return Campaign.brief_words


def brief_words(campaign: Campaign) -> str:
    """The brief's own words, as `campaign_document` reads them."""
    return f"{campaign.title} {campaign.description}"


def bio_words(creator: Creator) -> str:
    """The creator's own words, as `creator_document` reads them."""
    return creator.bio or ""


def words_of(text: str) -> ColumnElement[Any]:
    """The text's distinct stemmed words, read once per query. The text arrives as a
    bound parameter and is only cut into words, never parsed as query syntax."""
    return cast(
        select(_words(func.to_tsvector(_config(), text))).scalar_subquery(),
        ARRAY(Text),
    )


def shared_words(
    document: ColumnElement[Any], words: ColumnElement[Any]
) -> ColumnElement[Any]:
    """The distinct words the document shares with `words`, over the square root of
    the document's distinct words; 0 when it shares none."""
    lexemes = func.unnest(_words(document)).table_valued("word").render_derived()
    return (
        select(
            cast(func.count().filter(lexemes.c.word == any_(words)), Float)
            / func.sqrt(cast(func.greatest(func.count(), 1), Float), type_=Float)
        )
        .select_from(lexemes)
        .scalar_subquery()
    )


def rrf_score(
    distance: ColumnElement[Any] | None, keyword: ColumnElement[Any]
) -> ColumnElement[Any]:
    """The fused score, as a window over the filtered rows: each list ranks only the
    rows it can rank (a vector to compare; a word in common), as `fuse_ranks` does.
    `rank()`, not `row_number()` or `dense_rank()`: two rows a list cannot tell apart
    share a rank, so a tie stays a tie for the next rule (newest, past deals) to
    decide, and the row after them is placed by how many stand ahead of it."""
    terms = []
    if distance is not None:
        meaning = func.round(cast(distance, Numeric), MEANING_DECIMALS)
        by_meaning = func.rank().over(order_by=meaning.asc().nulls_last())
        terms.append(case((distance.is_(None), 0.0), else_=1.0 / (RRF_K + by_meaning)))
    by_words = func.rank().over(order_by=keyword.desc())
    terms.append(case((keyword > 0, 1.0 / (RRF_K + by_words)), else_=0.0))
    total: ColumnElement[Any] = terms[0]
    for term in terms[1:]:
        total = total + term
    return total
