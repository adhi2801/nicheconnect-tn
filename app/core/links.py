"""Links one person gives another: only to hosts we know (item 57, D-086).

A proof link or a dispute's evidence link is something the other side is
asked to open. Accepting any https address made each one a way to send a
brand or a creator to a fake login page, which is how most marketplace
phishing works (docs/standards/trust-and-safety.md section 2). Now a link
must be on a host from a published list, and everything a phishing link
relies on is refused:

- anything but https;
- a look-alike host: `instagram.com.evil.in` and `evilinstagram.com` are not
  instagram.com, because a host matches only exactly or as a subdomain;
- a name before an @ (`https://instagram.com@evil.in` goes to evil.in);
- non-Latin or punycode hosts (`xn--`), the homograph trick;
- a port, which no real post link carries.

The lists are policy, kept short on purpose: adding a host is a one-line
change with a reason, reviewed like code.
"""

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

# Where a creator's published post lives.
CONTENT_HOSTS: tuple[str, ...] = (
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "fb.watch",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "threads.net",
    "threads.com",
    "sharechat.com",
    "snapchat.com",
)
# Evidence in a dispute: a post, or a file kept where people keep receipts.
# These hosts can be misused too, but each is a well-known name the reader
# recognises; evidence uploaded to us, like proof files, is the better end.
EVIDENCE_HOSTS: tuple[str, ...] = (
    *CONTENT_HOSTS,
    "drive.google.com",
    "docs.google.com",
    "photos.google.com",
    "photos.app.goo.gl",
    "dropbox.com",
    "onedrive.live.com",
    "1drv.ms",
)


def host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    """The host is one on the list, or a subdomain of one (www., m.)."""
    return any(host == name or host.endswith("." + name) for name in allowed)


def checked_link(url: str, allowed: tuple[str, ...]) -> str:
    """The link, if it is safe to ask someone to open; otherwise a 422.

    Raises PydanticCustomError, so it can sit in a schema's validator and
    answer like every other invalid field.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        raise PydanticCustomError("link_not_https", "Use a full https:// link")
    if parts.username is not None or parts.password is not None or parts.port is not None:
        raise PydanticCustomError(
            "link_not_allowed", "Use the plain link the app's Share button gives you"
        )
    if not host.isascii() or any(label.startswith("xn--") for label in host.split(".")):
        raise PydanticCustomError(
            "link_not_allowed", "That link's address is not allowed"
        )
    if not host_allowed(host, allowed):
        raise PydanticCustomError(
            "link_host_not_allowed",
            "Links must be to {hosts}. For other files, upload them instead.",
            {"hosts": ", ".join(allowed)},
        )
    return url


def _content(url: str) -> str:
    return checked_link(url, CONTENT_HOSTS)


def _evidence(url: str) -> str:
    return checked_link(url, EVIDENCE_HOSTS)


# For schemas: a string that must be a link on the list.
ContentLink = Annotated[str, AfterValidator(_content)]
EvidenceLink = Annotated[str, AfterValidator(_evidence)]
