# Proposal: rate card, channels and media kit on the Creator Passport

**Status: Decisions 2–4 approved (D-042). Decision 1, the schema, still needs both founders.** Nothing here is built. Written 21 September 2026 by Adhi's session. Decision 3 changed after research; section 3 says why. The schema half is **Erode Harish's to own and implement**; the API half is Adhi's. The work is sequenced so no file is edited by both of you (section 6).

---

## 1. Why this, and why first

`docs/COMPETITIVE_LANDSCAPE.md` section 6 ranks this first, for three reasons:

- **It is now table stakes.** YouTube's Creator Partnerships (relaunched in India, March 2026) gives every creator a free **Media Kit** and **Desired Rates** inside YouTube Studio. Collabstr sells creator **packages** at fixed prices; Passionfroot and Beacons sell bookable media kits. A creator comparing us with those sees a gap today.
- **We can do what none of them can: put the price next to the proof.** A brand reading a creator's rate card here also sees their delivery record (D-038). A creator reading a brand's campaign already sees its payment record (D-034). No competitor holds both records, so none of them can show price and reliability on one screen.
- **It unlocks two more items on the list.** Audience size is what fair-rate guidance (#2) needs to be honest. A YouTube channel next to Instagram answers "we are Instagram-shaped and Tamil Nadu is not".

## 2. What people will see

**A creator** can:
- add their Instagram and YouTube channels, with follower count and average views. Brands always see these labelled "self-reported, as of <date>";
- list up to 10 packages, e.g. "1 Instagram Reel, ₹8,000, delivered in 5 days, 30 days' usage rights";
- decide whether their prices appear on their public Passport. Signed-in brands always see them.

**A brand** considering a creator gets one screen: the creator's public facts, channels, packages with prices, and delivery record. That is the media kit.

**The open internet**, on the public Passport link, sees **links to the channels themselves**, so anyone can check the real numbers at the source, and packages only if the creator switched them on. It never sees our copy of a follower count (D-042). It never sees the delivery record (D-038 point b stays open) or contact details (D-011).

**What it deliberately does not do:**
- No booking or paying through a package: we never move money (constraint 1).
- No scraped or estimated statistics: every number is the creator's own, labelled as such, until verification exists (item #6).
- No contact details, ever.

---

## 3. Decisions needed

```
DECISION NEEDED 1: Two new tables and one column (schema request)
Context:      Channels and packages are lists per creator with their own rules, so
              they are rows, not a JSON blob on the creator table.
Option A:     creator_channel + creator_package tables, plus creator.rate_card_public_at
              | + every rule enforced by the database; the export and future
                  references work per row
              | − one more migration in flight | effort M (Data track)
Option B:     One JSONB column on creator
              | + no new tables | − no per-field CHECKs, no FK for future references,
                  harder to query for fair-rate guidance | effort S
Recommended:  A. The database enforces what it can (database.md section 3).
Tables affected: creator_channel (new), creator_package (new), creator (+1 nullable column)
Migration:    one, "add creator channels and rate card"; additive only
Rollback:     downgrade drops both tables and the column. Loses creator-entered
              packages; acceptable because nothing is deployed
Data impact:  no existing row changes
→ Approve A, B, or modify?   (needs both founders; Erode Harish implements)
```

```
DECISION NEEDED 2: Who sees a creator's prices
Option A:     Signed-in brands always; the open internet only once the creator switches
              it on (rate_card_public_at, a consent timestamp like D-036)
              | + consent-first, matches D-036 | − one more switch | effort S
Option B:     Public by default
              | + more visible | − publishes someone's prices without asking,
                  and it cannot be undone once search engines have indexed it
Recommended:  A
APPROVED: A (D-042). Research: 73–78% of brands prefer creators with published
rates, and nano and micro creators gain most from publishing. So the sign-up
screen asks the question plainly. It is never a default, because DPDP is
consent-first.
```

```
DECISION NEEDED 3: Self-reported audience numbers in public
Option A:     Show them, always labelled "self-reported" with the date given
              | + useful now | − can be inflated (India's fake-follower rate is high)
Option B:     Brands only until verification exists
              | + nothing unverified in public | − the Passport stays thin
Recommended:  A. Labelled and dated, a claim is honest; hiding it helps nobody. The
              delivery and payment records are the real check on a creator, and they
              are built from facts.
APPROVED, CHANGED after research (D-042): neither A nor B. Follower counts are
the easiest number to fake, and about two in three Indian creators show
inflation. Republishing an unverifiable number under our name on the open
internet would lend it our credibility. So: the public page links to the
channel itself, where the real count lives. Signed-in brands see the
self-reported numbers, labelled and dated. The word "verified" is never used
for them.
```

```
DECISION NEEDED 4: The record next to the price
Option A:     The brand-facing media kit shows the delivery record (D-038) beside the
              packages; the public page does not
              | + the one thing no competitor can show | − none new: same access as D-038
Option B:     Keep them on separate screens
Recommended:  A
APPROVED: A (D-042), with one rule added: the records are never merged into a
single score. Averaging hides the one risk a brand needs to see.
```

---

## 4. Proposed schema (for Erode Harish to review and own)

Money is in whole paise (D-015); names follow `database.md` section 1. There is no `deleted_at`: a removed package is deleted outright, because the deletion policy waits on the DPDP answer (`database.md` section 3). Revisit once anything references a package.

### `creator_channel`: one row per creator per platform

| Column | Type | Rule |
|---|---|---|
| `id` | UUID | PK |
| `creator_id` | UUID | FK → `creator.id` **ON DELETE CASCADE** (a channel means nothing without its creator) |
| `platform` | VARCHAR(20) | `CHECK IN ('instagram', 'youtube')` |
| `profile_url` | VARCHAR(300) | `CHECK (profile_url LIKE 'https://%')`; the API also checks the domain matches the platform, so a public page cannot carry an arbitrary link |
| `followers` | INTEGER | `CHECK (followers >= 0)` |
| `average_views` | INTEGER NULL | `CHECK (average_views >= 0)`; nullable because not every creator knows it |
| `figures_as_of` | DATE | The Tamil Nadu date the creator last stated the numbers |
| `created_at`, `updated_at` | TIMESTAMPTZ | as every table |

`UNIQUE (creator_id, platform)`: one Instagram, one YouTube. The unique index also serves the foreign key.

No `source` column yet. Everything is self-reported until verification exists, and a CHECK listing a value nobody writes is a claim we have not kept (the D-033 principle).

### `creator_package`: one row per offer

| Column | Type | Rule |
|---|---|---|
| `id` | UUID | PK |
| `creator_id` | UUID | FK → `creator.id` **ON DELETE CASCADE** |
| `platform` | VARCHAR(20) | same CHECK as above |
| `format` | VARCHAR(20) | `CHECK IN ('post', 'reel', 'story', 'short', 'video', 'live', 'other')` |
| `title` | VARCHAR(80) | `CHECK (char_length(title) >= 1)` |
| `description` | TEXT NULL | `CHECK (char_length(description) <= 500)` |
| `price_paise` | BIGINT | `CHECK (price_paise > 0)` |
| `currency` | VARCHAR(3) | `CHECK (currency = 'INR')`, as elsewhere |
| `delivery_days` | SMALLINT | `CHECK (delivery_days BETWEEN 1 AND 90)` |
| `usage_rights_days` | INTEGER NULL | `CHECK (usage_rights_days BETWEEN 0 AND 3650)`, the same ceiling as the memo |
| `position` | SMALLINT | `CHECK (position BETWEEN 0 AND 19)`; display order |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

Index `(creator_id, position)`: the only query is "this creator's packages, in order", and it serves the foreign key too. The limit of 10 packages per creator is enforced in the API, because a database cannot count rows in a CHECK.

### `creator.rate_card_public_at`: TIMESTAMPTZ NULL

The consent itself, like `passport_published_at` (D-036): who chose, and when. NULL for everyone at first.

### Also required in the same change

- **Model tests** for every CHECK and the unique constraint.
- **Upgrade → downgrade → upgrade** round-trip, as CI already runs.
- The export completeness test will fail until both tables are either exported or explained. They must be exported: a creator's own rate card is their data.

---

## 5. Proposed API (Adhi, after the migration merges)

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/api/v1/creators/me/channels` | The creator | |
| PUT | `/api/v1/creators/me/channels/{platform}` | The creator | Upsert; `figures_as_of` set by the server, not the client |
| DELETE | `/api/v1/creators/me/channels/{platform}` | The creator | |
| GET | `/api/v1/creators/me/packages` | The creator | |
| POST | `/api/v1/creators/me/packages` | The creator | 409 at 10 packages |
| PATCH | `/api/v1/creators/me/packages/{package_id}` | The creator | Another creator's package is 404, never 403 |
| DELETE | `/api/v1/creators/me/packages/{package_id}` | The creator | |
| POST | `/api/v1/creators/me/rate-card/publish` and `/unpublish` | The creator | Mirrors the Passport switch (D-036): the first date is kept; unpublishing is never refused |
| GET | `/api/v1/creators/{creator_id}/media-kit` | Any brand, or the creator themself | Passport facts + channels + packages + delivery record, in a constant number of queries |
| GET | `/api/v1/creators/by-handle/{handle}` | Public (existing) | Gains `channels` (platform and link only, no counts) and `packages` only when published. Additive; the existing fields do not change |

All writes are rate limited at 30/min and reads at 60/min, and every `POST` and `PATCH` is retry-safe (D-040). Prices are integers in paise with the currency stated; the frontend formats them, in Tamil and English.

## 6. Who does what, in order

The CLAUDE.md overlap rules apply: no file is edited by both founders on the same day, and there is one migration in flight.

1. **Erode Harish:** the migration, the models and the model tests. **Only after reviewing PR #11**, so the migration chain stays linear (migrations 17–20 are on that branch).
2. **Adhi:** services, routers, schemas, API tests and export sections, once step 1 has merged.
3. **Then:** fair-rate guidance (#2 on the list) can start, because audience size exists.

## 7. Tests (testing.md section 1)

- **Each endpoint:** success; 422 validation; 401 without a token; 403 for the wrong role; 404 for another creator's package; rate limit.
- **Business rules:** 10-package limit; a domain that doesn't match the platform refused; the price never shown publicly before the switch and shown after it; unpublishing always allowed; the consent date kept on a second publish.
- **Media kit:** a constant query count whatever the number of packages; p95 measured on seeded data against the 300 ms budget.
- **Public Passport:** a contract test that the exact field set grows only by `channels` and `packages`, and that no follower or view count appears in it.
