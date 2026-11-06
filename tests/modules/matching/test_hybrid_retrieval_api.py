"""Hybrid retrieval: meaning and exact words, fused (learned matching step 1, D-167).

The rules worth proving: an exact word from the brief lifts a creator the
embedding cannot tell apart, on both sides of matching; the database's fused
order is exactly the rule `fusion.fuse` states; the rule itself keeps its
promises (first everywhere is first, the order of the lists does not matter,
ranking better never ranks you lower), ties included; the words are counted
once each, so repeating them or listing every word in a niche does not buy
a place; whether meaning ranked a list is said truly when only some rows
have a vector; a brief written in query syntax is read as words, never as a
query.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Float, column, select, update, values

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from app.modules.matching import embedder, fusion
from tests.factories import FIXED_NOW, build_brand, build_campaign, build_creator

PUBLISHED_AT = FIXED_NOW.replace(day=1)


class SameVector:
    """Every text the same vector: meaning cannot separate anyone, so only words can."""

    def encode(self, sentences, **kwargs):
        return [[0.5] * embedder.EXPECTED_DIMENSIONS for _ in sentences]


@pytest.fixture(autouse=True)
def only_this_tests_creators(db) -> None:
    db.execute(update(Creator).values(passport_published_at=None))


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def a_brand(db):
    brand = build_brand(db, email=f"h-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    token, _ = create_access_token(brand.account_id, "brand", FIXED_NOW)
    return brand, {"Authorization": f"Bearer {token}"}


def a_campaign(db, brand, **overrides):
    campaign = build_campaign(
        db,
        brand_id=brand.id,
        status="open",
        cities=["Madurai"],
        niches=["food"],
        **overrides,
    )
    db.add(campaign)
    db.flush()
    return campaign


def a_creator(db, bio, creator_id, published=True):
    creator = build_creator(
        db,
        id=creator_id,
        handle=f"h{uuid.uuid4().hex[:12]}",
        city="Madurai",
        niches=["food"],
        bio=bio,
        passport_published_at=PUBLISHED_AT if published else None,
    )
    db.add(creator)
    db.flush()
    return creator


FIRST_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
LAST_ID = uuid.UUID("ffffffff-ffff-4fff-bfff-ffffffffffff")


# --- the brand's side ---------------------------------------------------------------


def test_an_exact_word_from_the_brief_lifts_a_creator(client, db):
    brand, headers = a_brand(db)
    campaign = a_campaign(
        db,
        brand,
        title="Chettinad pepper chicken week",
        description="Home-style Chettinad.",
    )
    # Before fusion, equal creators came back by id: the plain one first.
    plain = a_creator(db, "Street food reels from my lane.", FIRST_ID)
    chettinad = a_creator(db, "Chettinad home cooking, slow and spicy.", LAST_ID)

    rows = client.get(f"/api/v1/campaigns/{campaign.id}/matches", headers=headers).json()

    assert [r["creator"]["id"] for r in rows["matches"]] == [
        str(chettinad.id),
        str(plain.id),
    ]


def test_words_and_meaning_together_once_both_are_indexed(client, db):
    from app.modules.matching import service

    embedder.set_model(SameVector())
    try:
        brand, headers = a_brand(db)
        campaign = a_campaign(
            db, brand, title="Biryani festival", description="Dum biryani."
        )
        plain = a_creator(db, "Street food reels.", FIRST_ID)
        biryani = a_creator(db, "Biryani in every town I visit.", LAST_ID)
        service.refresh_creators(db, creator_ids=[plain.id, biryani.id])
        service.refresh_campaigns(db, campaign_ids=[campaign.id])

        body = client.get(
            f"/api/v1/campaigns/{campaign.id}/matches", headers=headers
        ).json()
    finally:
        embedder.set_model(None)

    assert body["ranked_by_similarity"] is True
    assert [r["creator"]["id"] for r in body["matches"]] == [
        str(biryani.id),
        str(plain.id),
    ]


def test_a_brief_in_query_syntax_is_read_as_words(client, db):
    brand, headers = a_brand(db)
    campaign = a_campaign(
        db,
        brand,
        title="Snacks & sweets | !savoury :* (all)",
        description="'quote' <-> & | shop.example/menu?a=1&b=2",
    )
    plain = a_creator(db, "Street food reels from my lane.", FIRST_ID)
    sweets = a_creator(db, "Order at shop.example/menu?a=1&b=2 today.", LAST_ID)

    response = client.get(f"/api/v1/campaigns/{campaign.id}/matches", headers=headers)

    assert response.status_code == 200, response.text
    # the address, "&" and all, is one word the two share
    assert [r["creator"]["id"] for r in response.json()["matches"]] == [
        str(sweets.id),
        str(plain.id),
    ]


def test_saying_the_brief_s_words_again_adds_nothing(client, db):
    brand, headers = a_brand(db)
    campaign = a_campaign(
        db, brand, title="Chettinad pepper chicken week", description="Home-style."
    )
    once = a_creator(db, "Chettinad pepper chicken, cooked at home.", FIRST_ID)
    a_creator(
        db,
        "Chettinad chettinad chettinad pepper pepper chicken chicken, cooked at home.",
        LAST_ID,
    )

    rows = client.get(f"/api/v1/campaigns/{campaign.id}/matches", headers=headers).json()

    # tied on words, so the id decides: repetition did not lift the second
    assert rows["matches"][0]["creator"]["id"] == str(once.id)


def test_a_list_of_every_word_in_the_niche_does_not_beat_an_honest_bio(client, db):
    brand, headers = a_brand(db)
    campaign = a_campaign(
        db, brand, title="Chettinad pepper chicken week", description="Home-style."
    )
    a_creator(
        db,
        "food cooking recipes biryani chettinad chicken mutton fish curry dosa idli "
        "sambar rasam street cafe restaurant review baking desserts sweets snacks "
        "vegan healthy fitness travel lifestyle reels shorts",
        FIRST_ID,
    )
    honest = a_creator(db, "Chettinad chicken, my grandmother's way.", LAST_ID)

    rows = client.get(f"/api/v1/campaigns/{campaign.id}/matches", headers=headers).json()

    assert rows["matches"][0]["creator"]["id"] == str(honest.id)


# --- the creator's side -------------------------------------------------------------


def test_a_creator_sees_the_campaign_that_shares_their_words_first(client, db):
    brand, _ = a_brand(db)
    creator = a_creator(
        db, "Filter coffee and tiffin, every morning.", FIRST_ID, published=False
    )
    # Newest first would put the plain campaign first.
    coffee = a_campaign(
        db, brand, title="Filter coffee mornings", created_at=FIXED_NOW.replace(day=1)
    )
    plain = a_campaign(
        db, brand, title="Weekend specials", created_at=FIXED_NOW.replace(day=2)
    )
    token, _ = create_access_token(creator.account_id, "creator", FIXED_NOW)

    body = client.get(
        "/api/v1/campaigns/discover/for-me", headers={"Authorization": f"Bearer {token}"}
    ).json()

    # a laptop's seeded campaigns may share the city and niche, so the order
    # between these two is what is checked, not their absolute places
    order = [r["campaign"]["id"] for r in body["matches"]]
    assert order.index(str(coffee.id)) < order.index(str(plain.id))


# --- the rule, and the SQL that computes it -----------------------------------------

ids = st.lists(st.sampled_from("abcdefghij"), min_size=1, max_size=10, unique=True)


@given(st.lists(ids, min_size=1, max_size=3))
def test_first_in_every_list_is_first_overall(rankings):
    top = rankings[0][0]
    rankings = [[top, *[i for i in r if i != top]] for r in rankings]
    assert fusion.fuse(rankings)[0] == top


@given(st.lists(ids, min_size=2, max_size=3))
def test_the_order_of_the_lists_does_not_matter(rankings):
    assert fusion.fuse(rankings) == fusion.fuse(list(reversed(rankings)))


@given(ids, st.data())
def test_ranking_better_never_ranks_you_lower(ranking, data):
    if len(ranking) < 2:
        return
    i = data.draw(st.integers(min_value=1, max_value=len(ranking) - 1))
    item = ranking[i]
    promoted = ranking.copy()
    promoted[i - 1], promoted[i] = promoted[i], promoted[i - 1]
    other = data.draw(ids)
    before = fusion.fuse([ranking, other]).index(item)
    after = fusion.fuse([promoted, other]).index(item)
    assert after <= before


rows_strategy = st.lists(
    st.tuples(
        # four decimals, so the database's rounding of distances to six is exact;
        # a few shared values, so ties and several unranked rows are common
        st.none()
        | st.sampled_from([0.1, 0.2, 0.3])
        | st.integers(min_value=0, max_value=20_000).map(lambda n: n / 10_000),
        st.just(0.0)
        | st.sampled_from([0.25, 0.5])
        | st.floats(min_value=0.001, max_value=1.0, allow_nan=False),
    ),
    min_size=1,
    max_size=8,
)


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(rows_strategy)
def test_the_database_fuses_exactly_as_the_rule_states(db, rows):
    keyed = [(f"r{i}", d, t) for i, (d, t) in enumerate(rows)]
    table = values(
        column("rid"), column("d", Float), column("t", Float), name="ranked"
    ).data(keyed)
    score = fusion.rrf_score(table.c.d, table.c.t)
    got = list(db.scalars(select(table.c.rid).order_by(score.desc(), table.c.rid)))

    by_meaning = fusion.competition_ranks(
        {r: d for r, d, _ in keyed if d is not None}, best_first=False
    )
    by_words = fusion.competition_ranks(
        {r: t for r, _, t in keyed if t > 0}, best_first=True
    )
    fused = fusion.fuse_ranks([by_meaning, by_words])
    unranked = sorted(r for r, _, _ in keyed if r not in fused)
    assert got == fused + unranked


def test_the_scores_are_the_paper_s():
    scores = fusion.rrf_scores([{"a": 1, "b": 2}, {"b": 1}])
    assert scores == {"a": 1 / 61, "b": 1 / 62 + 1 / 61}
    assert fusion.fuse([["a", "b"], ["b"]]) == ["b", "a"]


def test_after_a_tie_the_next_rank_counts_everyone_ahead(db):
    # A and B tie first on meaning, so X is third, not second; W and Y rank
    # only by words. Y (1/62) must beat X (1/63); dense ranking would tie them.
    table = values(column("rid"), column("d", Float), column("t", Float), name="r").data(
        [
            ("A", 0.2, 0.0),
            ("B", 0.2, 0.0),
            ("X", 0.3, 0.0),
            ("W", None, 0.9),
            ("Y", None, 0.5),
        ]
    )
    score = fusion.rrf_score(table.c.d, table.c.t)
    got = list(db.scalars(select(table.c.rid).order_by(score.desc(), table.c.rid)))
    assert got == ["A", "B", "W", "Y", "X"]
    assert fusion.competition_ranks({"A": 0.2, "B": 0.2, "X": 0.3}, best_first=False) == {
        "A": 1,
        "B": 1,
        "X": 3,
    }


def test_meaning_closer_by_noise_alone_is_a_tie(db):
    # B's distance differs from A's by a billionth: noise, not meaning. With the
    # two tied on meaning, B's better word match must decide.
    table = values(column("rid"), column("d", Float), column("t", Float), name="r").data(
        [("A", 0.3, 0.5), ("B", 0.3 + 1e-9, 0.6)]
    )
    score = fusion.rrf_score(table.c.d, table.c.t)
    assert list(db.scalars(select(table.c.rid).order_by(score.desc(), table.c.rid))) == [
        "B",
        "A",
    ]


def test_the_list_says_it_is_ranked_by_meaning_when_a_row_has_no_vector(client, db):
    from app.modules.matching import service

    embedder.set_model(SameVector())
    try:
        brand, headers = a_brand(db)
        campaign = a_campaign(
            db, brand, title="Biryani festival", description="Dum biryani."
        )
        # Not embedded yet, but shares a word: ties the embedded creator at the
        # top (1/61 each) and wins on its id.
        unembedded = a_creator(db, "Biryani in every town.", FIRST_ID)
        embedded = a_creator(db, "Street food reels.", LAST_ID)
        service.refresh_creators(db, creator_ids=[embedded.id])
        service.refresh_campaigns(db, campaign_ids=[campaign.id])

        body = client.get(
            f"/api/v1/campaigns/{campaign.id}/matches", headers=headers
        ).json()
    finally:
        embedder.set_model(None)

    assert body["matches"][0]["creator"]["id"] == str(unembedded.id)
    assert body["matches"][0]["reasons"]["similarity"] is None
    assert body["ranked_by_similarity"] is True


def test_a_creator_s_list_is_ranked_by_meaning_when_a_campaign_has_no_vector(client, db):
    from app.modules.matching import service

    embedder.set_model(SameVector())
    try:
        brand, _ = a_brand(db)
        creator = a_creator(db, "Filter coffee every morning.", FIRST_ID)
        embedded = a_campaign(
            db, brand, title="Weekend specials", created_at=FIXED_NOW.replace(day=1)
        )
        # Newest, not embedded yet, sharing a word: ties at the top and is first.
        a_campaign(
            db, brand, title="Filter coffee mornings", created_at=FIXED_NOW.replace(day=3)
        )
        service.refresh_creators(db, creator_ids=[creator.id])
        service.refresh_campaigns(db, campaign_ids=[embedded.id])
        token, _ = create_access_token(creator.account_id, "creator", FIXED_NOW)

        body = client.get(
            "/api/v1/campaigns/discover/for-me",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    finally:
        embedder.set_model(None)

    assert body["matches"][0]["reasons"]["similarity"] is None
    assert body["ranked_by_similarity"] is True


def test_campaigns_equal_in_words_stay_newest_first(client, db):
    brand, _ = a_brand(db)
    creator = a_creator(db, "Filter coffee every morning.", FIRST_ID, published=False)
    older = a_campaign(
        db, brand, title="Filter coffee mornings", created_at=FIXED_NOW.replace(day=1)
    )
    newer = a_campaign(
        db, brand, title="Filter coffee mornings", created_at=FIXED_NOW.replace(day=2)
    )
    token, _ = create_access_token(creator.account_id, "creator", FIXED_NOW)

    body = client.get(
        "/api/v1/campaigns/discover/for-me", headers={"Authorization": f"Bearer {token}"}
    ).json()

    order = [r["campaign"]["id"] for r in body["matches"]]
    assert order.index(str(newer.id)) < order.index(str(older.id))


def test_equal_meaning_does_not_depend_on_the_order_rows_arrive_in(db):
    def order(rows):
        table = values(
            column("rid"), column("d", Float), column("t", Float), name="r"
        ).data(rows)
        score = fusion.rrf_score(table.c.d, table.c.t)
        return list(db.scalars(select(table.c.rid).order_by(score.desc(), table.c.rid)))

    a, b = ("A", 0.3, 0.0), ("B", 0.3, 0.0)
    assert order([a, b]) == order([b, a]) == ["A", "B"]
