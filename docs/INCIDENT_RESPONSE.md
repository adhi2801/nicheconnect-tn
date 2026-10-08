# When something goes wrong: the incident plan

**Written 8 October 2026 (D-082), for `docs/standards/security.md` section 9. Not yet rehearsed:** it must be walked through once, end to end, on staging before launch, and the rehearsal's date written here.

An incident is anything that may have exposed personal data or a secret, let someone act as another account, changed records nobody asked to change, or taken the API down. **When unsure, treat it as one.** Declaring an incident that turns out to be nothing costs an hour; waiting on a real one costs trust.

---

## 1. Who does what

| Role | Who | Does |
|---|---|---|
| Lead | Whoever notices first, until they hand over | Decides, keeps the log, says when it is over |
| Second | The other founder | Checks every step before it runs, takes over if the lead is unreachable |

Both founders are reached by phone call, not chat: a message can sit unread. If one cannot be reached within 30 minutes, the other proceeds alone and says so in the log.

**The log** is a private GitHub security advisory on this repository, opened at the start: times in IST, what was seen, what was done, who did it. It becomes the record and, if needed, the disclosure.

## 2. The first hour

1. **Open the log** (section 1). Write what was seen, and when.
2. **Stop the harm**, smallest step first:
   - one account abused: suspend it (admin API, D-061), which ends its sessions;
   - a secret leaked: rotate it (section 3);
   - the API itself unsafe: take it down (section 4).
3. **Keep the evidence.** Do not delete logs, rows, or the offending commit. Copy what you need into the advisory. Sentry events, CloudWatch logs and the admin log are the sources.
4. **Decide whether personal data was reached** (section 5). If it may have been, the notice clock may already be running.

## 3. Rotating each secret

Every secret lives in AWS Secrets Manager in staging and production, and in `.env` locally (`security.md` section 6). A leaked secret is rotated **even if the commit that leaked it was deleted**: the history is public.

| Secret | What rotating it breaks | How |
|---|---|---|
| `SECRET_KEY` (signs access tokens) | Every access token; apps refresh within 15 minutes and carry on | New 64-character random value in the app secret; redeploy |
| `OTP_HASH_KEY` | Login codes sent in the last 5 minutes | New value, different from `SECRET_KEY`; redeploy |
| Database password (in `DATABASE_URL`) | Nothing, if done in order | Change it in RDS, update the app secret, redeploy, confirm `/readyz` |
| `MSG91_AUTH_KEY` | Login codes until the new key is in | Regenerate in MSG91, update its secret, redeploy |
| `ANTHROPIC_API_KEY` | Results from proof, which retries | Revoke in the Anthropic console, new key into its secret, redeploy |
| `SENTRY_DSN` | Nothing (it only sends) | New client key in Sentry, revoke the old one |
| AWS access keys of a person | That person's console and CLI | Deactivate in IAM at once, then issue new ones |
| All refresh tokens (session theft) | Everyone is logged out | Revoke every session family through a reviewed Alembic data migration, never by hand (constraint 3); there is no admin route for this yet |

To end one person's sessions only, suspend and restore the account, or they use "log out everywhere".

## 4. Taking the API down safely

Set the API service's desired count to 0 in the ECS console (or `aws ecs update-service --desired-count 0` for the production cluster in `infra/envs/production`). The load balancer then answers 503 and nothing reaches the database. Background jobs run inside the same service (`RUN_JOBS`, D-060), so they stop with it. Bring it back by restoring the counts in OpenTofu (`tofu apply`), so the state in code and in AWS agree again.

Data is never deleted to stop an incident. A restore from backup (`docs/standards/database.md` section 8) is a decision both founders make, with the log open.

## 5. Telling people

- **Personal data may have been reached:** the Digital Personal Data Protection Rules require notice to the **Data Protection Board** and to **each person affected**, within the time the Rules set. The exact clock and wording come from the validation pack (constraint 6); until it confirms them, treat the notice as due **without delay** and ask the founders' adviser the same day.
- **Brands and creators affected:** told plainly by email and in the app: what happened, what it means for them, what we did, what they should do. No hedging and no blame.
- **The reporter, if it came from outside:** kept informed as `SECURITY.md` promises.
- **Nobody else** until the founders agree, and never a guess about cause stated as fact.

## 6. Afterwards

Within five working days, a short write-up in `docs/reports/`: the timeline, the cause, what stopped it, and the change that keeps it from happening again. The write-up blames no person. Every fix comes with a test that fails without it (`docs/standards/testing.md` section 2).

## 7. Rehearsal

| Date | Who | Scenario | What we changed |
|---|---|---|---|
| Not yet | Both founders | A leaked `SECRET_KEY` on staging, rotated and confirmed within the hour | |
