"""What holds for every body and every If-None-Match (RFC 9110 section 13.1.2)."""

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
