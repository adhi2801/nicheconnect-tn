"""An answer's version (ETag), and whether the reader already holds it.

Public reads (the Passport, the city figures, the festival templates) send
an ETag, a hash of exactly the body, so a reader who sends it back in
`If-None-Match` gets a 304 with no body. RFC 9110 section 13.1.2 has that
header compared weakly, against a list, `*` included: a proxy that
compresses an answer marks its ETag weak (`W/"..."`), and nginx does, so an
exact string comparison never matched behind one and every read cost a full
body (audit C7, 7 November 2026).
"""

import hashlib


def etag_for(body: bytes) -> str:
    """A strong ETag for exactly these bytes."""
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def _opaque(tag: str) -> str:
    """The tag without its weakness mark, for the weak comparison."""
    tag = tag.strip()
    return tag[2:] if tag.startswith("W/") else tag


def holds_current(if_none_match: str | None, etag: str) -> bool:
    """Whether `If-None-Match` names `etag`, so a 304 may answer it."""
    if if_none_match is None:
        return False
    if if_none_match.strip() == "*":
        return True
    current = _opaque(etag)
    return any(_opaque(tag) == current for tag in if_none_match.split(","))
