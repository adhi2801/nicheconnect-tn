# Infrastructure: AWS Mumbai, written as code (D-062, D-063)

Everything the backend runs on is described here, in OpenTofu 1.12.6, and
nothing is created by hand in the AWS console. A change to the servers is a
change to these files, reviewed as a pull request like any other.

**Nothing here has been applied yet.** It needs an AWS account, which only a
founder can open.

## What it builds, per environment

| Piece | What | Where |
| --- | --- | --- |
| Network | a VPC over two availability zones, public and private subnets | `modules/app/network.tf` |
| Database | RDS PostgreSQL 18, encrypted, point-in-time backups, private | `modules/app/data.tf` |
| Cache | ElastiCache Valkey 9.1, TLS and a password, private | `modules/app/data.tf` |
| Files | a private, encrypted, versioned S3 bucket, TLS only | `modules/app/data.tf` |
| Secrets | generated keys and connection strings in Secrets Manager | `modules/app/secrets.tf` |
| Images | two registries, `api` and `embeddings`, immutable tags, scanned on push | `modules/app/secrets.tf` |
| Front door | a TLS 1.3 certificate and an HTTPS load balancer; HTTP only redirects | `modules/app/edge.tf` |
| App | ECS Fargate: the API service (with the job runner inside, D-060), a migration task, and the daily embeddings refresh | `modules/app/compute.tf` |

`envs/staging` and `envs/production` use the same module and differ only in
size and safety settings. Staging can be torn down; production has deletion
protection and two weeks of backups.

## Going live, in order

**Only a founder can do steps 1, 2, 5, 8 and 9.**

1. **Open the AWS account** in the company's name, secure the root user with
   MFA, and create a separate administrator login for daily use.
2. **Install OpenTofu 1.12.6** and sign in to AWS on your machine
   (`aws configure sso`, or an access key for that administrator).
3. **The state bucket**, once ever:
   ```
   cd infra/bootstrap
   tofu init
   tofu apply
   ```
   Note the `state_bucket` it prints.
4. **Staging**, with the git commit of the image to run and the API's name:
   ```
   cd infra/envs/staging
   tofu init -backend-config="bucket=<state_bucket>"
   tofu plan -var "image_tag=<commit>" -var "domain_name=<api staging name>"
   tofu apply  (same -var values)
   ```
   The first apply creates the image registries; the images are pushed to
   them next, and the service starts once they exist.
5. **DNS**: add the `certificate_validation_records` it prints, and point the
   API's name at `load_balancer_dns_name` with a CNAME. HTTPS works from then.
6. **Push the images** (`docker build --target api` and `--target
   embeddings`, tagged with the commit) to the two registries it printed.
7. **Migrate**, by running the `migrate_task_definition` once in the
   cluster, in the `task_network` it printed. It is the release step
   (`app/db/prepare.py`, item 97): the migrations, DBOS's schema, and the
   app's own database login, `nicheconnect_app`, which may only read and
   write rows. It is the only task that connects as the database owner. Then
   the service starts healthy. Run it before every deploy.
8. **Logins**: paste the MSG91 key into the secret named in
   `msg91_secret_name`, then apply again with `-var "otp_sender=msg91"` and
   `-var "msg91_whatsapp_number=<number>"`.
9. **Report deadline alerts** (item 51, D-103). The IT Rules give some
   reports 2 hours, and the warning job tells the founders through error
   tracking, so it reaches nobody until both of these are done:
   - apply again with `-var "sentry_dsn=<the project's DSN>"`;
   - in Sentry, add an issue alert: *the event's message contains*
     `report.`, *the issue is seen more than 0 times in 1 minute*, then
     *email every founder* (and later page them). Sentry's default alert
     fires only on a new issue, and every warning of one kind ("due soon",
     or "late") is one issue, so without this rule only the first warning of
     each kind would ever email.
   Then file an `impersonation` report on staging, wait 1 hour 35 minutes,
   and confirm the email and the admin's `report_due_soon` notification
   arrive.
10. **Test a restore from backup** before the first real user (D-062).
11. **Rehearse the incident plan** on staging, end to end, and write the date in `docs/INCIDENT_RESPONSE.md` section 7: a leaked `SECRET_KEY` rotated and confirmed within the hour.
12. **Production**: the same steps in `infra/envs/production`.
13. **Admins** (D-061, D-105), in each environment. An admin logs in with
    two factors, so each one is made, then given a one-time setup ticket.
    Run the script as a one-off task of the **API's** task definition (its
    login may write rows, which is all this needs), in the `task_network` it
    printed, with the command overridden:
    ```
    aws ecs run-task --cluster nicheconnect-staging --launch-type FARGATE --task-definition nicheconnect-staging-api --network-configuration "<task_network>" --overrides '{"containerOverrides":[{"name":"api","command":["python","scripts/make_admin.py","+91XXXXXXXXXX","--yes"]}]}'
    ```
    then again with `--second-factor` added. The ticket is printed in the
    task's log in CloudWatch: it works once, for 15 minutes, and only with a
    code sent to that admin's phone, so a copy left in the log is useless
    once redeemed. The admin redeems it at `POST
    /api/v1/auth/admin/second-factor` and puts the secret into an
    authenticator app **on a different device from the admin phone, or one
    locked by fingerprint, and not one that copies codes to a cloud
    account** (Retool's 2023 breach went through such a copy). Aegis
    (Android) or 2FAS are free. A lost or locked authenticator is the same
    `--second-factor` step; every admin is told whenever it is run. Only a
    founder with AWS access, itself behind MFA (step 1), can do this.

**Later, not part of going live: results read from proof (D-070).** Off
until the validation pack says a creator's insights may go to a processor.
Then paste the Claude API key into the secret named in
`anthropic_secret_name`, and apply again with
`-var "proof_reading_enabled=true"`. Switched on before the key is pasted,
the app refuses to start and ECS rolls the deploy back.

**Later, not part of going live: the UPI pay link (D-085).** Off until the
validation pack supplies the notice creators read before giving their UPI ID.
Then apply again with `-var "upi_notice_version=<its version>"`. Withdrawing
a UPI ID works whatever this is set to.

**Later, not part of going live: connected Instagram and YouTube accounts
(D-134).** Off until Meta App Review and Google's verification approve the
apps, and the validation pack supplies the notice creators read before
connecting. Meta's review needs the domain, the live website, a privacy policy
URL and Meta Business Verification first. Then register the website's
`<base>/instagram` and `<base>/youtube` as the apps' redirect URIs, and Meta's
callbacks as `https://<api>/api/v1/platforms/meta/data-deletion` and
`.../deauthorize`; paste the two secrets into the ones named in
`meta_app_secret_name` and `google_client_secret_name`; and apply again with
`-var "platform_connections_enabled=true" -var "platform_redirect_base=<base>"
-var "meta_app_id=<id>" -var "google_client_id=<id>"
-var "connect_notice_version=<its version>"`. Switched on with anything
missing or a secret still a placeholder, the app refuses to start and ECS
rolls the deploy back. Disconnecting works whatever this is set to.

## Rules

- **State holds every generated password.** It lives only in the encrypted
  state bucket. Never commit a `.tfstate` file; `.gitignore` refuses them.
- **Images are named by git commit, never `latest`**, and the registries
  refuse to overwrite a tag, so a running version can always be traced back
  to its code.
- **Provider versions are locked** (`.terraform.lock.hcl`, for Linux and
  Windows), so every machine applies with byte-identical providers.
- **Logs are kept 180 days, in Mumbai**, as CERT-In's Directions require of
  every company (D-086, `docs/standards/legal.md` section 3.2). The module
  refuses a shorter `log_retention_days`.
- **CI checks these files on every push**: `tofu fmt -check` and `tofu
  validate` on the bootstrap and both environments, against the locked
  providers, with no AWS credentials (D-086).
- **A NAT gateway is deliberately not used** (about $35 a month per
  environment). The app's containers have public addresses for outbound calls
  only; their security group accepts nothing except the load balancer. See
  `modules/app/network.tf`.
