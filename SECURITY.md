# Security policy

Brands and creators trust this service with their business records and their contact details. If you have found a way to break that trust, we want to hear it first, and we will treat you as a partner.

## Reporting a vulnerability

**Report privately through GitHub:** [open a private security advisory](https://github.com/adhi2801/nicheconnect-tn/security/advisories/new). Only the founders see it. Please do not open a public issue, pull request or discussion about it.

Include, as far as you can:

- what is affected (an endpoint, a file, a workflow) and what an attacker gains;
- the steps to reproduce it, with requests and responses, using **your own test accounts only**;
- the version or commit you tested, and when.

This address is also published in [`/.well-known/security.txt`](https://www.rfc-editor.org/rfc/rfc9116) on the API.

## What happens next

| Step | Our target |
|---|---|
| We confirm we have your report | 3 working days |
| We tell you whether it is a vulnerability, and how severe (CVSS 4.0) | 10 working days |
| Fixed, for critical and high severity | 30 days from confirmation |
| Fixed, for medium and low | 90 days, or sooner in a normal release |

We keep you told as it moves, credit you in the advisory if you wish, and agree a disclosure date with you, normally once a fix is live and at most 90 days after the report.

We are two founders, not a security team. These are targets we hold ourselves to, and we will tell you plainly if one slips.

## Scope

**In scope:** this repository and the API it builds, including login, tokens, permissions between brands and creators, personal data, proof files, the deal record, and the CI and supply chain in `.github/`.

**Out of scope:**

- denial of service, load or volume testing, and spam;
- social engineering of founders, users or providers, and physical attacks;
- findings in services we use (AWS, GitHub, MSG91, Sentry), which go to them;
- missing headers or settings with no exploit shown;
- anything requiring a compromised device or an already stolen token.

## Safe harbour

If you act in good faith, stay within this policy, use only accounts you own, access no more data than you need to show the problem, never change or delete others' data, and give us reasonable time to fix it, we will not pursue or support legal action against you for your research. If you reach someone else's personal data by accident, stop, do not keep it, and tell us in your report.

We cannot pay bounties yet.

## Supported versions

Only the current `main` branch and the API running from it receive fixes.

## How we protect the code

What we already enforce, and what is still owed before launch, is written down in [`docs/standards/security.md`](docs/standards/security.md): the target is OWASP ASVS 5.0 Level 2.
