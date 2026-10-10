"""Links one person asks another to open: only to hosts we know (item 57).

Each refused case is a real phishing trick, so each is its own test case.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.links import CONTENT_HOSTS, EVIDENCE_HOSTS, ContentLink, EvidenceLink

content = TypeAdapter(ContentLink)
evidence = TypeAdapter(EvidenceLink)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/abc123/",
        "https://instagram.com/p/abc/",
        "https://m.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://www.facebook.com/reel/123",
        "https://x.com/priya/status/1",
        "https://www.threads.net/@priya/post/1",
        "https://www.linkedin.com/posts/priya_1",
    ],
)
def test_a_post_on_a_known_platform_passes(url):
    assert content.validate_python(url) == url


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://www.instagram.com/reel/abc/", "link_not_https"),
        ("instagram.com/reel/abc", "link_not_https"),
        ("javascript:alert(1)", "link_not_https"),
        ("https://evil.in/instagram.com/reel", "link_host_not_allowed"),
        ("https://instagram.com.evil.in/reel/abc", "link_host_not_allowed"),
        ("https://evilinstagram.com/reel/abc", "link_host_not_allowed"),
        ("https://instagram.com@evil.in/reel/abc", "link_not_allowed"),
        ("https://user:pass@instagram.com/reel", "link_not_allowed"),
        ("https://instagram.com:8443/reel/abc", "link_not_allowed"),
        ("https://xn--nstagram-yjb.com/reel/abc", "link_not_allowed"),
        ("https://\u0456nstagram.com/reel/abc", "link_not_allowed"),  # Cyrillic i
        ("https://bit.ly/3abc", "link_host_not_allowed"),
        ("https://drive.google.com/file/d/1/view", "link_host_not_allowed"),
    ],
    ids=[
        "plain http",
        "no scheme",
        "javascript",
        "host only in the path",
        "look-alike suffix",
        "look-alike prefix",
        "name before an at sign",
        "credentials",
        "a port",
        "punycode",
        "homograph",
        "a shortener",
        "a file host is not a post",
    ],
)
def test_a_phishing_shape_is_refused_with_its_reason(url, code):
    with pytest.raises(ValidationError) as refused:
        content.validate_python(url)

    assert refused.value.errors()[0]["type"] == code


def test_evidence_may_also_be_a_file_where_people_keep_receipts():
    assert evidence.validate_python("https://drive.google.com/file/d/1/view")
    assert evidence.validate_python("https://www.dropbox.com/s/abc/receipt.png")
    with pytest.raises(ValidationError):
        evidence.validate_python("https://receipts-upi-help.in/r/1")


def test_the_refusal_names_the_hosts_that_are_allowed():
    with pytest.raises(ValidationError) as refused:
        content.validate_python("https://evil.in/x")

    assert "instagram.com" in str(refused.value)


def test_every_content_host_is_also_evidence():
    assert set(CONTENT_HOSTS) <= set(EVIDENCE_HOSTS)
