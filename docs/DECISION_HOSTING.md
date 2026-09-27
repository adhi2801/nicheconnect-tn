# Decision needed: where the backend runs, and where uploaded files live

**Status: needs Adhi's decision.** Researched 27 September 2026. Nothing is
set up, and no account has been opened anywhere.

## Why now

**Nothing is deployed.** Every endpoint runs only on a laptop, so no creator
or brand can reach any of it, the MSG91 sender has nowhere to run, the job
runner's daily timestamps (D-060) never fire, and the designers have no
staging server to build against. Hosting is the one decision that turns the
backend into something people can use.

**File storage comes with it.** Profile photos, brand logos, proof
screenshots and media-kit images all need somewhere to live, and the answer
belongs next to the servers. It also unblocks E3 (resumable uploads).

## What we need from hosting

| Need | Why |
| --- | --- |
| **A region in India** | Latency for users in Tamil Nadu. Whether DPDP ever *requires* Indian storage for us is a validation-pack question (constraint 6); an Indian region avoids needing the answer. |
| **Managed PostgreSQL 18 with pgvector 0.8.2 or newer** | D-049 and the plan's row: CVE-2026-3172 (CVSS 8.1) affects pgvector 0.6.0 to 0.8.1. |
| **Managed Valkey** | Rate limits and idempotency (D-048). |
| **Containers**, at least 2 GB of memory per app instance | The app runs DBOS inside it (D-060), and matching loads a 0.6B-parameter embedding model through torch (D-052). |
| **Private object storage** with signed upload links | Uploads go straight from the phone to storage, never through our server. |
| **Automated backups with point-in-time restore**, and one tested restore | Backlog section 5 lists "backup and one tested restore" as not started because it waited on this. |
| **A secrets store** | The MSG91 key, the token keys and the OTP key must never sit in a file on a server. |
| **Staging and production**, separately | Designers build against staging; real users never touch it. |

## The options

**A. AWS, Mumbai (ap-south-1).** *Recommended.*
- **Database:** Amazon RDS for PostgreSQL 18, which
  [runs pgvector 0.8.2](https://www.usage.ai/blogs/aws/reserved-instances/rds/postgresql/extensions-cost/),
  the version that fixes the CVE. Automated backups and point-in-time
  restore are built in.
- **Cache:** ElastiCache for Valkey, which
  [runs Valkey 9.1](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-elasticache-valkey-9-1/),
  the version we already run locally (D-048).
- **App:** containers on ECS Fargate behind a load balancer. No servers to
  patch.
- **Files:** S3 in Mumbai, private, with signed upload links. CloudFront, or
  Cloudflare with its Chennai point of presence, in front of public images
  later.
- **Secrets:** Secrets Manager, with keys encrypted by KMS.
- **Why it is best:** every need above is met by a managed service in one
  region, the compliance paperwork (ISO 27001, SOC 2) exists when a large
  brand asks, it is what the plan already recommends, and it grows without
  moving. **The cost is set-up effort**: it has the most parts to wire, which
  is why it should be written as code (below) rather than clicked together.

**B. DigitalOcean, Bangalore.**
- Managed PostgreSQL
  [supports pgvector on 14 to 18](https://1bench.dev/extensions/postgresql/on-digitalocean),
  [managed Valkey](https://www.digitalocean.com/products/managed-databases-valkey),
  App Platform for the containers, Spaces for files.
- **Simpler and cheaper**, perhaps half of A for a pilot.
- **But:** I could not confirm which pgvector *version* it runs, which is the
  one thing the CVE makes non-negotiable, and it offers less of what a large
  brand's security review asks for. It would be a move later rather than a
  place to grow.

**C. Google Cloud, Mumbai.**
- Cloud Run and Cloud SQL for PostgreSQL 18 are good products, but Cloud SQL's
  pgvector was
  [last reported at 0.8.1](https://docs.cloud.google.com/sql/docs/postgres/release-notes),
  inside the CVE's range, and Cloud Run in `asia-south1` was
  [listed as by invitation](https://docs.cloud.google.com/run/docs/locations).
  Both may have changed; neither is a risk worth starting with.

**Not considered:** Neon (no India region, per the plan); Supabase (has
Mumbai, but runs its own platform around Postgres that we would not use);
anything without managed Postgres 18.

## What it costs (estimates, to be checked in AWS's own calculator)

For a pilot, production sized small and staging smaller:

| Piece | Production | Staging |
| --- | --- | --- |
| RDS PostgreSQL 18, small instance, 20 GB | about $30 | about $15 |
| ElastiCache Valkey, smallest node | about $12 | about $12 |
| ECS Fargate, 1 vCPU and 2 GB, always on | about $35 | about $20 |
| Load balancer | about $20 | about $20 |
| S3, Secrets Manager, logs | under $10 | under $5 |
| **Roughly** | **$105 a month** | **$70 a month** |

About **₹15,000 a month for both**, before GST and before any credits.
**These are my estimates from published prices, not a quote**; the real
figure comes from AWS's calculator with the exact choices, and should be
checked before anything is opened. AWS Activate offers startup credits that
could cover the first months; whether the company qualifies is for you to
check. Staging can be switched off when nobody is using it.

## How it would be built, once chosen

- **Infrastructure as code with OpenTofu**, the open-source Terraform, kept
  in this repository and reviewed like any other change. Nothing is clicked
  together by hand, so every environment can be rebuilt from the repository
  and every change has a diff. Adding it is a dependency decision of its own,
  asked when the first file is written.
- CI builds one image, runs migrations as a separate step, and deploys to
  staging on merge; production deploys only by a founder's hand.
- A restore from backup is tested before the first real user, not after the
  first incident.

## Decisions needed

```
DECISION NEEDED: hosting and file storage
Option A: AWS Mumbai (RDS PostgreSQL 18 + pgvector 0.8.2, ElastiCache Valkey
          9.1, ECS Fargate, S3, Secrets Manager)
          | + every need met in one Indian region; grows without moving
          | − most set-up work; about $175 a month for both environments
Option B: DigitalOcean Bangalore
          | + simpler, cheaper | − pgvector version unconfirmed; a move later
Recommended:  A.
Risk & rollback: nothing is committed until the code for it is reviewed;
          before real users, tearing it down costs only what was used.
→ Approve A or B?
```

**Only you can do, if A:** open the AWS account in the company's name, with
the company's billing; turn on multi-factor sign-in for the root user and
then never use it; apply for AWS Activate credits; and decide who else gets
access. I will write everything else, as code, for review.

## Sources

[RDS pgvector and pricing](https://www.usage.ai/blogs/aws/reserved-instances/rds/postgresql/extensions-cost/) ·
[Amazon RDS for PostgreSQL 18](https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-rds-postgresql-major-version-18/) ·
[ElastiCache Valkey 9.1](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-elasticache-valkey-9-1/) ·
[CVE-2026-3172](https://www.sentinelone.com/vulnerability-database/cve-2026-3172/) ·
[DigitalOcean pgvector](https://1bench.dev/extensions/postgresql/on-digitalocean) ·
[DigitalOcean Valkey](https://www.digitalocean.com/products/managed-databases-valkey) ·
[Cloud SQL release notes](https://docs.cloud.google.com/sql/docs/postgres/release-notes) ·
[Cloud Run locations](https://docs.cloud.google.com/run/docs/locations)
