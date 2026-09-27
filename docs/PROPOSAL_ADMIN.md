# Proposal: the admin side, so the pilot can be run

**Status: option A approved in principle by Adhi (26 September 2026); this
design needs his yes before anything is built.** Written 27 September 2026 on
`feature/admin`, stacked on `feature/creator-search`.

## 1. What it is for

Four things the founders must be able to do from day one of a pilot, none
of which is possible today without hand-editing the database (which
constraint 3 forbids):

1. **Find an account** when someone phones: by phone number or handle.
2. **Suspend an account** (a fake profile, a brand not paying, abuse), and
   restore it.
3. **Handle reports**: users flag a profile or a campaign; an admin sees
   the queue and resolves each one.
4. **See what admins did**: every admin action and every look at personal
   data, on an append-only log.

Out of scope, on purpose: editing users' content, reading deal fees or
messages, refunds (we never hold money), and dashboards or charts.

## 2. Who is an admin, and how they log in

- **A third account role, `admin`.** An admin account has no brand or
  creator profile.
- **Admins are only ever created by a local command**,
  `scripts/make_admin.py <phone>`, run by a founder on a machine with database
  access. There is no sign-up path and no API to promote anyone.
- **Admins log in the same way as everyone**, with a WhatsApp code, sending
  `role: "admin"`. **Login never creates an admin**: if no admin account
  exists for that phone, the answer is identical to a wrong code, so the
  endpoint cannot be used to find out who the admins are.
- **Shorter sessions:** an admin's refresh token lasts 1 day, not 30.
- **An admin cannot suspend an admin**, including themself; that is a
  founder's job at the database, through the same command.

## 3. Suspension

- `account.suspended_at` and `account.suspension_reason`. **Suspended means
  stopped at once, everywhere**: every request reloads the account, so a
  suspended account's next request gets `403 account_suspended`, even with a
  token that has not expired. Its refresh tokens are revoked at the moment
  of suspension.
- **A suspended creator disappears** from search, matching and the public
  Passport. **A suspended brand's campaigns disappear** from discovery.
- **Existing deals are not deleted or changed.** The other party can still
  see them, mark or confirm payment, and open a dispute. Suspending a
  brand must never become a way for a creator to lose the record of what
  they are owed.
- The suspended person is told why, in the error: the reason category, never
  the admin's private note.
- **Restoring** clears both columns and puts everything back.

## 4. Reports

- Any signed-in user can report a **creator profile, a brand or a
  campaign**, with a category (`fake_profile`, `spam`, `abuse`,
  `non_payment`, `other`) and an optional note of up to 1,000 characters.
- One open report per reporter per subject: reporting twice updates nothing
  and says so.
- Admins list reports (open first, oldest first) and resolve each one as
  `actioned` or `dismissed`, with a note. The reporter is not told who the
  admin was.
- Rate limited at 10 reports an hour per account, so reporting cannot be
  used to flood the queue.

## 5. The admin log

Every admin action, and **every time an admin opens an account's personal
details** (its phone number), is written to `admin_action`, append-only by
trigger like the deal record: who, what, which subject, why, when. Admins
can read the log; nobody can change it. It is how a founder answers "who
looked at my number, and why?", which DPDP makes a fair question to ask.

## 6. The schema (schema request)

```
account                    two new columns, and a wider role check
  role                     CHECK role IN ('brand', 'creator', 'admin')
  suspended_at             TIMESTAMPTZ NULL
  suspension_reason        VARCHAR(40) NULL, CHECK in the report categories
  CHECK (suspended_at IS NULL) = (suspension_reason IS NULL)

report                     one row per report
  id                       UUID, uuidv7()
  reporter_account_id      UUID, FK -> account, ON DELETE CASCADE
  subject_kind             VARCHAR(20), CHECK in ('creator', 'brand', 'campaign')
  subject_id               UUID            (no FK: it points at one of three tables)
  category                 VARCHAR(20), CHECK in the five categories
  note                     TEXT NULL, <= 1000 characters
  status                   VARCHAR(20), CHECK in ('open', 'actioned', 'dismissed')
  resolved_at              TIMESTAMPTZ NULL
  resolution_note          TEXT NULL, <= 1000 characters
  created_at, updated_at
  UNIQUE (reporter_account_id, subject_kind, subject_id) WHERE status = 'open'
  INDEX (status, created_at) for the queue

admin_action               append-only by trigger
  id                       UUID, uuidv7()
  admin_account_id         UUID, FK -> account, ON DELETE RESTRICT
  action                   VARCHAR(30), CHECK in ('view_account', 'suspend',
                           'restore', 'resolve_report')
  subject_account_id       UUID NULL
  report_id                UUID NULL
  note                     TEXT NULL, <= 1000 characters
  created_at               TIMESTAMPTZ
  INDEX (created_at)

Migration:   one revision. Existing rows are untouched: nobody is an admin or
             suspended until someone makes it so.
Rollback:    downgrade drops the two tables and the columns, and narrows the
             role check back. It refuses if any admin account exists, so a
             rollback cannot silently orphan one.
Data impact: small; one row per report and per admin action.
```

## 7. Endpoints

| Method and path | Who | What |
| --- | --- | --- |
| `POST /api/v1/reports` | Any signed-in brand or creator | Report a creator, brand or campaign |
| `GET /api/v1/admin/accounts?phone=` or `?handle=` | Admin | Find an account; **logged as `view_account`** |
| `GET /api/v1/admin/accounts/{id}` | Admin | Role, profile, suspension, counts of deals and reports; **logged** |
| `POST /api/v1/admin/accounts/{id}/suspend` | Admin | With a category and a note |
| `POST /api/v1/admin/accounts/{id}/restore` | Admin | With a note |
| `GET /api/v1/admin/reports?status=open` | Admin | The queue, oldest first, cursor-paged |
| `POST /api/v1/admin/reports/{id}/resolve` | Admin | `actioned` or `dismissed`, with a note |
| `GET /api/v1/admin/actions` | Admin | The log, newest first |

All admin routes: admin role only, everyone else **404**, so the admin API
cannot be discovered by probing. Rate limited like other endpoints. **Admins
never see** login codes, tokens, deal fees, dispute notes, or anything a
creator typed into a deal.

## 8. What needs your answer

```
DECISION NEEDED: the admin side as designed above
Approve:     the schema in section 6, the endpoints in section 7, and the
             rules in sections 2 to 5
Open for the validation pack (not guessed): how long reports and the admin
             log are kept, and whether a suspended person must be offered
             an appeal route under DPDP.
→ Reply "yes" to build it as written, or name what to change.
```

## 9. Build plan, once approved

1. Migration, models, model tests (every CHECK, the partial unique index,
   the trigger, the guarded downgrade).
2. `make_admin.py`, and admin login through the existing code flow, with
   the "never creates" and "no enumeration" tests first.
3. Suspension: enforcement in the one place every request passes, hiding
   from search, matching, the public page and discovery, and the rule that
   existing deals stay usable by the other side.
4. Reports and the admin endpoints, every one writing to the log.
5. Full suite, coverage, the fuzz, and a decision entry.
