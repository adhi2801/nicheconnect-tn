# Proposal: notification preferences, and invite and source attribution

**Status: proposed, 8 October 2026. Not built.** Both were approved in principle by D-071 ("built before launch"); each needs a new table, so each needs a schema approval (`CLAUDE.md` section 5) before code. Attribution also touches sign-up, which is the security gate. Items 18 and 21 in `docs/BACKEND_COMPLETE.md`.

---

## 1. Notification preferences (item 18)

### Why now

More than six notifications a week makes a user 3.4 times as likely to uninstall within 30 days (D-071's source). Push and WhatsApp delivery are not built yet (item 9, device tokens), but the preferences decide how they are built: a sender written without quiet hours gets quiet hours bolted on later.

### What it governs

**Only delivery outside the app** (push, WhatsApp, later email). The in-app list keeps every notification, always: it is the record of what happened, and nobody should be able to miss a payment because they muted something.

**Urgent events cannot be muted or held**, whatever the settings: anything with a deadline running against the person. These are `memo_sent` (an answer is due), `proof_submitted` (the review window runs), `proof_revision_requested`, `payment_marked_paid` (the creator's confirmation window runs), and the dispute events once they exist. Everything else may be muted, held for quiet hours, or rolled into a digest.

### The table

```
notification_preference          one row per account; no row = the defaults
  account_id        uuid  PK, FK account(id) ON DELETE CASCADE
  quiet_from        time  NULL     -- IST; both set or both NULL (CHECK)
  quiet_until       time  NULL
  digest            text  NOT NULL DEFAULT 'off'   -- 'off' | 'daily' (CHECK)
  digest_hour       smallint NOT NULL DEFAULT 19   -- 0..23 IST (CHECK)
  muted_types       text[] NOT NULL DEFAULT '{}'   -- CHECK: no urgent type
  created_at, updated_at  timestamptz
```

- **Migration:** one new table, no change to existing rows. **Downgrade:** drop the table. **Data impact:** none; everybody reads the defaults until they save.
- **Endpoints:** `GET /api/v1/me/notification-preferences` (the defaults when no row), `PUT` the same (whole object, idempotent).
- **In the export** (`/me/export`), as everything about a person is.

```
DECISION NEEDED: the defaults
Option A: quiet hours 22:00–08:00 IST on for everyone, digest off | + matches how people sleep; nothing urgent is held | − a few non-urgent pings wait until morning | effort S
Option B: no quiet hours until the person sets them | + nothing ever waits | − night pings are the top uninstall cause | effort S
Recommended: A, because only non-urgent events are held, and those can wait 10 hours.
Risk & rollback: a default is one constant; changing it later changes only people who never saved.
```

---

## 2. Invite and source attribution (item 21)

### Why now

Attribution not recorded at sign-up can never be recovered (D-071). The pilot's whole question is which channel works: Instagram, WhatsApp groups, CODISSIA events, Passport links, or one creator bringing a brand.

### The tables

```
invite_code                      one per account, made on first request
  code         text  PK          -- 8 characters, no look-alikes (no 0/O, 1/I)
  account_id   uuid  UNIQUE, FK account(id) ON DELETE CASCADE
  created_at   timestamptz

account_attribution              written once, at sign-up, never changed
  account_id         uuid  PK, FK account(id) ON DELETE CASCADE
  invite_code        text  NULL, FK invite_code(code) ON DELETE SET NULL
  source             text  NOT NULL   -- 'invite' | 'passport_link' | 'instagram'
                                      -- | 'whatsapp' | 'event' | 'search' | 'other'
                                      -- | 'not_given' (CHECK)
  campaign_tag       text  NULL       -- e.g. 'codissia-oct'; [a-z0-9-]{1,40}
  created_at         timestamptz
```

- **Sign-up change (security gate):** `POST /auth/otp/verify` accepts optional `invite_code`, `source` and `campaign_tag` **only when it creates a new account**; a returning login ignores them, so nobody can rewrite how they arrived. An unknown or own code is ignored, never an error (a typo must not block sign-up).
- **Endpoints:** `GET /api/v1/me/invite-code` (made on first call); `GET /api/v1/me/invites` (how many people joined with my code, by role, as counts only); an admin view of sign-ups by source and week.
- **Migration:** two new tables. **Downgrade:** drop both. **Data impact:** none on existing accounts (they read `not_given`).

```
DECISION NEEDED: what an inviter may see
Option A: counts only ("3 brands and 5 creators joined with your code") | + no one's identity revealed without their say | − a creator cannot thank a brand by name | effort S
Option B: names of who joined | + warmer | − tells one person that another joined, a DPDP question for the validation pack | effort S
Recommended: A, because B needs the validation pack's answer and A loses nothing a reward needs.
Risk & rollback: widening to B later is one endpoint; narrowing after names were shown is impossible.
```

**Rewards are not part of this.** Recording who invited whom makes a reward possible later; what the reward is, and its tax treatment, is a founder and validation-pack question (constraint 6).

---

## 3. What approval builds

Approving both, with the recommended options, builds: 3 tables in 2 migrations (one at a time, so the chain cannot fork), 6 endpoints, the sign-up change, the export additions, and tests for each, including that an urgent event can never be muted and that a returning login cannot rewrite its attribution.
