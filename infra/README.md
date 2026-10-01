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

**Only a founder can do steps 1, 2, 5 and 8.**

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
   cluster, in the `task_network` it printed. Then the service starts
   healthy.
8. **Logins**: paste the MSG91 key into the secret named in
   `msg91_secret_name`, then apply again with `-var "otp_sender=msg91"` and
   `-var "msg91_whatsapp_number=<number>"`.
9. **Test a restore from backup** before the first real user (D-062).
10. **Production**: the same steps in `infra/envs/production`.

**Later, not part of going live: results read from proof (D-070).** Off
until the validation pack says a creator's insights may go to a processor.
Then paste the Claude API key into the secret named in
`anthropic_secret_name`, and apply again with
`-var "proof_reading_enabled=true"`. Switched on before the key is pasted,
the app refuses to start and ECS rolls the deploy back.

## Rules

- **State holds every generated password.** It lives only in the encrypted
  state bucket. Never commit a `.tfstate` file; `.gitignore` refuses them.
- **Images are named by git commit, never `latest`**, and the registries
  refuse to overwrite a tag, so a running version can always be traced back
  to its code.
- **Provider versions are locked** (`.terraform.lock.hcl`, for Linux and
  Windows), so every machine applies with byte-identical providers.
- **A NAT gateway is deliberately not used** (about $35 a month per
  environment). The app's containers have public addresses for outbound calls
  only; their security group accepts nothing except the load balancer. See
  `modules/app/network.tf`.
