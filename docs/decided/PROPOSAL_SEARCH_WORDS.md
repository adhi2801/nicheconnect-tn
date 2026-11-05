# Creator search in plain words (item 64, D-158)

**Status: Approved by Adhi on 5 November 2026 (D-158), under his standing instruction to build without asking; built the same day on `feature/search-words`. Not reviewed by Erode Harish (D-051).** Kept as the reasoning behind the build.

## What it does

A brand types "café creators in Coimbatore, 5k to 20k followers, free on 14 November". `GET /api/v1/creators/search-reading` answers search's own filters (food, Coimbatore, 5,000 to 20,000 followers, free on 14 November), which words became each one, the words it did not use, and why, where there is a reason. The screen shows each filter as a chip to remove, then runs the ordinary search.

## How it reads

Fixed rules in `app/modules/matching/words_reader.py`, in passes, each consuming its words so no later pass reads them again: quoted words (searched in the bio), days, prices, followers, platforms and formats, niches, places, and what is left.

- **Days** come before numbers, so "14 November" is never 14 followers, and a year must look like one and never be followed by a range or "followers" ("November 14, 2050 to 5000 followers" is 2,050 to 5,000). A day without a year is the next one; a passed day, 31 February and a whole month are refused with a note.
- **Money** needs ₹, Rs, INR, rupees or "budget", so ₹10k is never an audience. Search finds creators priced up to an amount, so "from ₹2000" is refused with a note, and "₹5k to ₹15k" keeps the higher amount.
- **Followers** need "followers" (or subscribers, fans) or a unit (k, lakh, million): "over 50" says nothing. "5 to 20k" is 5,000 to 20,000; "20k to 5k" is still that range. "Micro influencers" is refused with a note: the tiers mean different sizes to different people.
- **Places** are every city a creator the brand could find wrote, and Tamil Nadu's 38 districts and a few large towns with their other spellings (`place_names.py`). A place is sent as the spelling most of those creators used.
- **Search takes one of each.** A second niche, city, platform, format, price or day is returned unread with a note. The same thing twice is one filter.
- **What is left** is filler ("creators in", "who", "Tamil Nadu") or unread, as written. "Tamil" alone is unread: it may mean a language, which search cannot filter on.

## The twelve dimensions (D-098, D-139)

| Dimension | |
|---|---|
| Quality | 91 fixed examples of the rules and their traps; four property tests that any text up to 200 characters stays within search's own limits and reports only words it was given, and that any search a brand could mean, written in any order and any known form, reads back exactly with nothing left; API tests for the reading, finding what was meant, the spelling chosen, blocks, team members, every refusal, the rate limit and the query count; 17 rules broken on purpose, each caught (four first missed and got tests: a word ending in "at" before a price, a filler city, the low end above the high, the lookalike letters) |
| Novelty | TikTok One's Creator AI Search (13 May 2026) and Modash's AI search read words with a model and show a shortlist. Ours names the words behind every filter and says what it did not understand, reads the same words the same way every time, keeps them on our servers, and its results carry only dated statements and verified figures |
| Architecture | `matching` (layer 5): `words_reader` (the rules, no database), `place_names`, `words_service` (the places, one query), `words_router`, `words_schemas`. Nothing new to deploy; `ARCHITECTURE_SCALE.md` unchanged |
| Research | The competitors above, read 5 November 2026; Tamil Nadu's 38 districts; Python's case-insensitive matching of "İ", "ı", "ſ" and the Kelvin sign as ASCII letters, which a lookup must fold the same way (found while writing the property tests) |
| Security | Spoofing: brands only, through the one access check. Tampering: nothing is written. Repudiation: nothing to deny. Disclosure: places come only from creators the viewer could find (`visible`), so a block or a takedown hides a creator's city too; a team member reads as the brand. Denial of service: search's limit, 30 a minute and 600 a day; 200 characters at most; patterns without nested repetition, run on any text by the property tests. Elevation: a read, open to every member |
| Privacy & law | The words are not stored, logged beyond the access log's query string, or sent anywhere. No personal data. `legal.md` unchanged |
| Trust & safety | It reads only what search already shows; it cannot reach a creator search could not |
| Performance | One query per reading, however many creators (a test proves it). p95 in `docs/PERFORMANCE.md` |
| Design | Two calls: read the words, then search with the filters. Chips from `read_as`, a line for `unread`, notes from the message catalogue |
| Business | Search a brand can use in its own words, the first thing it does; no cost per search, unlike a model |
| Reliability | No outside call; nothing to retry. A failure is a 500 the property tests make unlikely: any text was run through it |
| Maintainability | Additive route; new niche words, places and note codes are additions, and clients show an unknown note by its words. A model could sit behind the same response later |
