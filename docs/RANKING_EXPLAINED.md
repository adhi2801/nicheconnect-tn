# How Colyv orders the people and campaigns it suggests

The text of the public page the Consumer Protection (E-Commerce) Rules ask for: the main things that move someone up a list, most important first (`docs/standards/legal.md` section 3.4). The website shows this page as written here. It changes in the same change as the ranking code it describes, and each section says which code that is.

**What never moves anyone up:** money. Nobody can pay to be placed higher, and we sell no placement.

---

## A campaign's suggested creators

*Shown to the brand that owns the campaign. Code: `app/modules/matching/service.py`, `find_creators_for_campaign`; `app/modules/matching/fusion.py`. Last changed 6 November 2026 (D-167).*

**Who can appear at all.** Only creators who chose to publish their profile, who live in a city the campaign names, and who share at least one of its niches. Never a creator either side has blocked, an account that is suspended, or a profile withheld on an order.

**Then, in this order:**

1. **Free to take work now.** Creators who are free today come before creators booked until a later date. A booked creator still appears, with the date they are free from.
2. **How well their profile fits the brief.** Two things count equally:
   - how close the creator's profile is in meaning to what the brand wrote;
   - how many of the brief's own words the creator used in describing their work (an exact dish, a place, a style).
3. **Deals they have agreed before**, more first, when two creators fit equally well.

---

## Campaigns suggested to a creator

*Shown to the creator, for themselves only. Code: `app/modules/matching/service.py`, `find_campaigns_for_creator`; `app/modules/matching/fusion.py`. Last changed 6 November 2026 (D-167).*

**Which campaigns can appear at all.** Open campaigns, still taking applications, in the creator's city and sharing at least one of their niches, from a brand that is not suspended or blocked by either side, that the creator has not already applied to.

**Then, in this order:**

1. **How well the campaign fits the creator.** Two things count equally:
   - how close the brief is in meaning to the creator's profile;
   - how many of the creator's own words the brief uses.
2. **Newest first**, when two campaigns fit equally well.

---

*Other lists that order people (creator search, "like my best") are described here as each next changes; until then their order is stated in the API's own documentation.*
