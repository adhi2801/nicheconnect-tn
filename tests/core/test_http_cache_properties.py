"""What holds for every body and every If-None-Match (RFC 9110 section 13.1.2)."""

import hashlib
import re

from hypothesis import given
from hypothesis import strategies as st

from app.core.http_cache import etag_for, holds_current

bodies = st.binary(max_size=200)


@given(body=bodies)
def test_a_tag_matches_itself_strong_or_weak(body):
    tag = etag_for(body)

    assert holds_current(tag, tag)
    assert holds_current(f"W/{tag}", tag)
    assert holds_current(f" {tag} ", tag)


@given(body=bodies, others=st.lists(bodies, max_size=4), at=st.integers(min_value=0))
def test_a_tag_anywhere_in_a_list_matches(body, others, at):
    tags = [etag_for(o) for o in others]
    tags.insert(at % (len(tags) + 1), etag_for(body))

    assert holds_current(", ".join(tags), etag_for(body))


@given(body=bodies, other=bodies)
def test_another_bodys_tag_never_matches(body, other):
    if body == other:
        return
    assert not holds_current(etag_for(other), etag_for(body))
    assert not holds_current(f"W/{etag_for(other)}", etag_for(body))


@given(body=bodies)
def test_no_header_never_matches_and_star_always_does(body):
    assert not holds_current(None, etag_for(body))
    assert holds_current("*", etag_for(body))


@given(body=bodies)
def test_a_tag_is_the_bodys_hash_quoted_as_rfc_9110_says(body):
    """An entity-tag is a quoted string (RFC 9110 section 8.8.3); ours, the
    first 32 hex digits of the body's SHA-256. Mutation testing found no test
    held its shape (8 November 2026)."""
    tag = etag_for(body)

    assert re.fullmatch(r'"[0-9a-f]{32}"', tag)
    assert tag == f'"{hashlib.sha256(body).hexdigest()[:32]}"'
