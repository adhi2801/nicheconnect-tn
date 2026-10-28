"""A Passport as search engines read it: schema.org ProfilePage (item 85, D-121). Pure.

Google's ProfilePage guidance (read 24 October 2026) is for pages about a
person who posts on the site: our creators. It needs the person's name, and
recommends the handle (`alternateName`), an identifier that survives a new
handle, a description, the dates the profile was made and last changed, and
links to the person's other profiles (`sameAs`).

Built only from what the creator published on their Passport (D-036), field
by field: never contact details, never a figure. Google allows only
statistics counted by the hosting platform itself, and a creator's follower
numbers are what they told us, so none are given. The website adds the
page's own URL when it embeds this.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA_CONTEXT = "https://schema.org"


@dataclass(frozen=True)
class PassportFacts:
    """What a published Passport shows, as the structured data needs it."""

    creator_id: uuid.UUID
    handle: str
    display_name: str
    bio: str | None
    created_at: datetime
    last_modified: datetime
    channel_urls: Sequence[str]


def last_modified(
    created_or_updated: Sequence[datetime | None],
) -> datetime:
    """The latest of the times given: when what a reader sees last changed."""
    return max(moment for moment in created_or_updated if moment is not None)


def profile_page(facts: PassportFacts) -> dict[str, Any]:
    """The ProfilePage JSON-LD object for one published Passport."""
    person: dict[str, Any] = {
        "@type": "Person",
        "name": facts.display_name,
        "alternateName": facts.handle,
        "identifier": str(facts.creator_id),
    }
    if facts.bio:
        person["description"] = facts.bio
    if facts.channel_urls:
        person["sameAs"] = list(facts.channel_urls)
    return {
        "@context": SCHEMA_CONTEXT,
        "@type": "ProfilePage",
        "dateCreated": facts.created_at.isoformat(),
        "dateModified": facts.last_modified.isoformat(),
        "mainEntity": person,
    }
