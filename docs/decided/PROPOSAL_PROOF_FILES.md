# Proposal: proof of delivery as files, not only links (E3)

**Status: proposed, 30 September 2026. Nothing here is built or approved.**

## 1. Why

A creator proves delivery today by pasting an `https://` link
(`deliverable_proof.content_url`). If the post is deleted, archived or made
private, the proof goes with it, and proof is the one thing a dispute needs
(D-036). Brands also ask for screenshots of reach and insights, which have no
link at all.

What this adds: a creator attaches **screenshots or photos** to a proof. The
files live in our private S3 bucket (D-062), the deal record keeps each file's
fingerprint, and the brand views them through short-lived links.

**Already decided, not reopened here:** files go straight from the phone to
S3 through signed upload links, never through our server (D-062). Our API
also refuses request bodies over 1 MB (`app/core/body_limit.py`), so nothing
else would work anyway.

## 2. How it works

1. **Ask to upload.** `POST /api/v1/deal-memos/{id}/proof/uploads` with the
   file's type, size and SHA-256 fingerprint. We check the creator owns the
   deal and the limits (section 3), save an `upload` row as `pending`, and
   answer with a signed S3 form valid for 10 minutes. The form itself
   enforces the size range, the type and the fingerprint: **S3 refuses a file
   that does not match what was declared**, so a different file cannot be
   swapped in.
2. **Upload.** The phone sends the file directly to S3.
3. **Submit the proof** with the upload ids (and a link, now optional). We
   check each object exists in S3 with the declared size and fingerprint,
   attach it to the proof, and seal the fingerprints into the deal record
   (D-057).
4. **Clean the file.** A background job (DBOS, D-060) re-encodes each image:
   it removes every piece of metadata, including GPS location, and writes a
   clean copy; the original is deleted. The brand sees the proof as soon as
   it is submitted; each file shows once cleaned, within seconds.
5. **View.** The brand and the creator get links valid for 5 minutes. Nobody
   else can see the files; the bucket is private (D-062).

Abandoned uploads (asked for, never submitted) are deleted by an S3 rule after
one day.

## 3. Limits for the pilot

| Limit | Value | Why |
| --- | --- | --- |
| File types | JPEG, PNG, WebP | Screenshots and photos. The apps convert iPhone HEIC to JPEG before upload |
| Size per file | 10 MB | A full-resolution phone photo fits; anything larger is not a screenshot |
| Files per proof | 10 | Enough for a reel's insights and a few stills |
| Upload links per creator | 30 an hour | Rate limited like every endpoint (constraint 4) |
| Video | **Not in the pilot** | Large, slow on mobile data, and cannot be cleaned cheaply. A link covers video for now |

## 4. Decisions needed

```
DECISION NEEDED 1: Remove location and hidden data from every image
Context:  A photo sent as a file keeps its GPS location unless something strips
          it. WhatsApp keeps 100% of it when a photo is sent as a document.
          Proof photos are often taken at home.
Option A: We re-encode every image on the server (a background job) and keep
          only the clean copy | + location never reaches a brand, whatever
          app or setting the creator used; also defuses files disguised as
          images | − one new package (Pillow) and a job | effort M
Option B: Trust the apps to strip it before upload | + nothing on the server
          | − one old app version or web upload leaks a home address | effort S
Option C: Keep files as uploaded | − the leak above, by design | effort 0
Recommended: A. It is the only option where a mistake elsewhere cannot leak
          a creator's home.
Risk & rollback: Pillow has regular security advisories, and pip-audit fails CI
          on any (testing.md gate 6), so it must be kept current. Rollback:
          stop the job; files stay private either way.
```

```
DECISION NEEDED 2: How we test it, and what runs on a laptop
Context:  MinIO, the usual local stand-in for S3, stopped publishing free
          images in October 2025 and archived its repository in early 2026.
Option A: Tests use an in-memory stand-in behind one storage seam (like the
          embedder's), plus moto (AWS's S3 imitation) for the S3 code itself.
          Local S3 waits until frontend work needs it, then SeaweedFS in
          docker-compose (Apache 2.0) | + no new service now; nothing
          unmaintained | − one dev-only package (moto) | effort S
Option B: SeaweedFS or Garage in docker-compose now, and tests against it
          | + closest to real S3 | − a new service in compose and CI now,
          before anyone needs it | effort M
Recommended: A.
Risk & rollback: moto can differ from real S3 in corner cases; the first
          staging deploy is the real check. Rollback: remove the package.
```

```
DEPENDENCY REQUEST
Package:     boto3 (runtime)
Why:         Signs upload and view links and checks objects in S3. AWS's own library
Alternatives: signing requests by hand (security code we should not write);
             obstore (newer, less proven); no package (not possible)
Security/maintenance: maintained by AWS, released several times a week; audited
             by pip-audit like every package

Package:     Pillow (runtime)
Why:         Decision 1, option A: re-encoding images
Alternatives: pyvips (faster, needs a system library in the image);
             none (options B or C)
Security/maintenance: widely used; frequent security releases, so it must be
             upgraded promptly (pip-audit enforces that)

Package:     moto (development only)
Why:         Decision 2, option A: tests the S3 code without AWS
Alternatives: SeaweedFS in compose (option B); no S3 tests (not acceptable)
Security/maintenance: dev only; never in an image
```

```
SCHEMA REQUEST
Tables affected: new table `proof_file`: id, deal_memo_id, proof_id (null
             until submitted), uploader account, S3 key, content type, size
             in bytes, SHA-256, status (pending, attached, cleaned, rejected),
             created, attached and cleaned times. Indexed on deal_memo_id and
             proof_id; one partial index for the cleaner's queue.
             `deliverable_proof.content_url` becomes optional, with a check
             that a proof has a link or at least one file.
Migration:   one migration, constraints added NOT VALID then validated
             (Squawk, D-050)
Rollback:    downgrade drops the table and restores content_url as required;
             it refuses while any proof has files and no link
Data impact: none on existing rows; every existing proof has a link
```

**Also needed (infrastructure, same approval):** the bucket's CORS rule so the
website can upload, the task role allowed to sign, read and delete in the
uploads prefix only, and the one-day expiry rule for abandoned uploads. All in
`infra/`, none applied until AWS exists.

## 5. Privacy and retention

- The deal record stores only fingerprints, never the files. So a file can be
  deleted later, when an account is deleted (E8) or after a retention period,
  without breaking the record's chain (D-057). The fingerprint still proves
  what was shown.
- **How long to keep proof files is a validation pack question** (DPDP,
  constraint 6). Until it is answered: kept while the deal is open or
  disputed, and never used for anything but the deal.
- Files never go near matching or embeddings (constraint 2).

## 6. Cost

About ₹0 at pilot scale. S3 in Mumbai costs roughly $0.025 a GB a month
(estimate from published prices): 1,000 proofs of five 2 MB screenshots is
10 GB, about ₹20 a month. Data coming into S3 is free; each upload or view request costs a small fraction of a paisa.
No paid scanning service is needed while only re-encoded images are stored.
Scanning (GuardDuty Malware Protection for S3, $0.09 a GB in US East after the
February 2025 price cut) is for when video arrives.

## 7. Build order, once approved

Each step is one commit with its tests:

1. The storage seam, its S3 version and its test stand-in (boto3, moto)
2. The `proof_file` table and migration
3. Asking to upload, and submitting a proof with files
4. The cleaning job (Pillow)
5. View links for the brand and the creator
6. Infrastructure: CORS, task role permissions, expiry rule

## Sources

- [MinIO Community Edition images discontinued](https://github.com/lobehub/lobehub/issues/9845), [MinIO moves away from open source (It's FOSS)](https://itsfoss.com/news/minio-moves-away-from-open-source/)
- [boto3 `generate_presigned_post`](https://docs.aws.amazon.com/botocore/latest/reference/services/s3/client/generate_presigned_post.html)
- [SHA-256 checksum with a presigned upload (AWS re:Post)](https://repost.aws/questions/QUgivVIUn6QrGVpETR1wQ4KQ/s3-sha256-checksum-for-presigned-url-in-file-upload)
- [GuardDuty Malware Protection for S3 price reduction (AWS)](https://aws.amazon.com/about-aws/whats-new/2025/02/amazon-guardduty-malware-protection-s3-price-reduction)
- [What metadata WhatsApp strips and keeps](https://metadatacleaner.app/blog/whatsapp-photo-metadata/)
