"""A brand's plain words read as creator-search filters (item 64, D-158).

The rules are `words_reader`'s and take no database. This supplies the one
thing they need from it: the places, as the creators a brand could find
actually wrote them. Search compares a city exactly (ignoring case), so
"Trichy" must be sent as whichever spelling most of those creators used.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models.creator import Creator
from app.modules.matching.place_names import PLACES
from app.modules.matching.search_service import visible
from app.modules.matching.words_reader import Reading, place_key, read


def cities_for(db: Session, viewer_account_id: uuid.UUID | None) -> dict[str, str]:
    """Each place name a brand may write, folded, mapped to the spelling to search.

    One query. Only creators the viewer could find count (`visible`), so a
    blocked or withheld creator's city never shapes the answer.
    """
    rows = db.execute(
        select(func.min(Creator.city), func.count())
        .where(*visible(viewer_account_id))
        .group_by(func.lower(Creator.city))
    ).all()
    written: dict[str, tuple[str, int]] = {}
    for city, count in rows:
        key = place_key(city)
        seen = written.get(key)
        written[key] = (seen[0], seen[1] + count) if seen else (city, count)

    cities = {key: city for key, (city, _) in written.items()}
    for group in PLACES:
        keys = [place_key(name) for name in group]
        used = [written[key] for key in keys if key in written]
        # The spelling most of them wrote; the usual name when nobody is there yet.
        target = max(used, key=lambda pair: pair[1])[0] if used else group[0]
        cities.update(dict.fromkeys(keys, target))
    return cities


def read_words(
    db: Session, words: str, viewer_account_id: uuid.UUID | None, today: date
) -> Reading:
    """The search filters `words` ask for, how each was read, and what was not."""
    return read(words, cities=cities_for(db, viewer_account_id), today=today)
