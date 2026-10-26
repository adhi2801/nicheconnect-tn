"""Properties of assistants' tokens and their scopes (item 11, D-138), over generated inputs."""

import hashlib
import hmac

from hypothesis import given
from hypothesis import strategies as st

from app.core.config import settings
from app.modules.auth import agent_tokens
from app.modules.auth.agent_scopes import ANY_SCOPE, SCOPE_ROUTES, allows
from app.modules.auth.models.agent_token import AGENT_SCOPES

scope_lists = st.lists(st.sampled_from(AGENT_SCOPES), max_size=8)
routes = st.sampled_from(sorted(set(ANY_SCOPE).union(*SCOPE_ROUTES.values())))


@given(scope_lists, st.randoms())
def test_the_value_a_code_binds_ignores_order_and_repeats(scopes, rng):
    shuffled = list(scopes)
    rng.shuffle(shuffled)

    assert agent_tokens.scopes_value(shuffled + scopes) == agent_tokens.scopes_value(
        scopes
    )


@given(scope_lists, scope_lists)
def test_different_scopes_bind_different_values(first, second):
    same = set(first) == set(second)

    assert (agent_tokens.scopes_value(first) == agent_tokens.scopes_value(second)) == same


@given(scope_lists, scope_lists, routes)
def test_more_scopes_never_reach_less(scopes, more, route):
    if allows(scopes, *route):
        assert allows(scopes + more, *route)


@given(scope_lists, routes)
def test_a_route_is_reached_only_through_a_scope_listing_it(scopes, route):
    reached = allows(scopes, *route)

    assert reached == (
        route in ANY_SCOPE or any(route in SCOPE_ROUTES[scope] for scope in scopes)
    )


@given(st.text(max_size=60))
def test_only_a_token_with_the_prefix_takes_the_assistant_path(text):
    assert agent_tokens.is_agent_token(text) == text.startswith("nct_")


@given(st.integers(min_value=0, max_value=50))
def test_every_new_token_is_distinct_and_hashes_to_the_stored_format(_):
    first, second = agent_tokens.new_agent_token(), agent_tokens.new_agent_token()

    assert first != second
    assert first.startswith("nct_") and len(first) == len("nct_") + 43
    digest = agent_tokens.hash_agent_token(first)
    assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")
    assert digest != agent_tokens.hash_agent_token(second)


@given(st.text(max_size=80))
def test_the_stored_hash_is_keyed_and_labelled(token):
    key = settings.otp_hash_key.get_secret_value().encode()
    expected = hmac.new(
        key, b"agent-token\x00" + token.encode(), hashlib.sha256
    ).hexdigest()

    assert agent_tokens.hash_agent_token(token) == expected
    # Never the bare digest anyone could work out from a copy of the table.
    assert expected != hashlib.sha256(token.encode()).hexdigest()
