"""A search read from plain words, on the wire (item 64, D-158)."""

from datetime import date

from pydantic import BaseModel, Field

from app.core.taxonomy import Niche
from app.modules.auth.schemas import ChannelPlatform, PackageFormat
from app.modules.matching.words_reader import Filter, NoteCode, Reading


class SearchFiltersRead(BaseModel):
    """Each is the query parameter of the same name on `GET /api/v1/creators`;
    pass the ones that are not null, unchanged."""

    q: str | None = Field(
        description="Words in the handle, name or bio: only what was in quotes",
        examples=["millet"],
    )
    niche: Niche | None = Field(examples=["food"])
    city: str | None = Field(
        description="Spelled as most creators there wrote it", examples=["Coimbatore"]
    )
    platform: ChannelPlatform | None = Field(examples=["instagram"])
    min_followers: int | None = Field(examples=[5000])
    max_followers: int | None = Field(examples=[20000])
    max_price_paise: int | None = Field(
        description="In paise: ₹1 is 100", examples=[1000000]
    )
    format: PackageFormat | None = Field(examples=["reel"])
    available_on: date | None = Field(
        description="A Tamil Nadu day, today or later", examples=["2026-11-14"]
    )


class ReadPartRead(BaseModel):
    words: str = Field(
        description="The brand's own words, as written", examples=["5k to 20k followers"]
    )
    filter: Filter = Field(
        description=(
            "The filter they became. A range gives two parts with the same words. "
            "New filters may be added: show an unknown one as its words"
        ),
        examples=["min_followers"],
    )
    value: str = Field(
        description="What was read, as the query parameter takes it", examples=["5000"]
    )


class SearchNoteRead(BaseModel):
    code: NoteCode = Field(
        description=(
            "Why some words were not used. `a_month_is_not_a_day`: search checks "
            'one day, so name one. `tier_needs_numbers`: "micro" and the like '
            "mean different sizes to different people, so give a follower range. "
            "`price_from_not_searchable`: search finds creators priced up to an "
            "amount, not from one. `free_needs_a_day`: say which day. "
            "`day_has_passed`, `not_a_real_day`, `number_out_of_range`: as named. "
            "`one_…`: search takes one of each; the first was used. New codes "
            "may be added: show an unknown one by its words alone"
        ),
        examples=["a_month_is_not_a_day"],
    )
    words: str = Field(examples=["free in December"])


class SearchReadingRead(BaseModel):
    """How a brand's words were read. Short lists: the words are at most 200 characters."""

    filters: SearchFiltersRead
    read_as: list[ReadPartRead] = Field(
        description="Which words became which filter, in the order written"
    )
    unread: list[str] = Field(
        description=(
            "Words not used, as written, in order: nothing was guessed from them"
        ),
        examples=[["vegan"]],
    )
    notes: list[SearchNoteRead] = Field(description="Why, where there is a reason")


def to_read(reading: Reading) -> SearchReadingRead:
    f = reading.filters
    return SearchReadingRead(
        filters=SearchFiltersRead(
            q=f.q,
            niche=f.niche,
            city=f.city,
            platform=f.platform,
            min_followers=f.min_followers,
            max_followers=f.max_followers,
            max_price_paise=f.max_price_paise,
            format=f.format,
            available_on=f.available_on,
        ),
        read_as=[
            ReadPartRead(words=p.words, filter=p.filter, value=p.value)
            for p in reading.parts
        ],
        unread=list(reading.unread),
        notes=[SearchNoteRead(code=n.code, words=n.words) for n in reading.notes],
    )
