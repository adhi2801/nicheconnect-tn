# The postmortem template

**For:** whichever founder led an incident, to write it up afterwards; the other founder, who reviews it. **Written 11 November 2026 (D-185)**, with `docs/standards/backend.md` section 0 and `docs/INCIDENT_RESPONSE.md` section 6, which say when a postmortem is due. **Not yet used:** nothing is deployed, so no incident has happened. A test that holds every postmortem to this template is owed (`docs/BACKEND_COMPLETE.md` item 148).

**The bar:** Google's postmortem culture ("An unreviewed postmortem might as well never have existed", *Site Reliability Engineering*, "Postmortem Culture") and Atlassian's incident handbook (named approvers; the fixes for a cause due within 4 or 8 weeks). Sources in `backend.md` section 13.

## How to use it

1. **When one is due:** user-visible downtime past the threshold, any data loss, a fix by hand during the incident (a rollback, a reroute, a restore), a resolution that took too long, or monitoring that missed it (Google's five); and every security incident and every personal-data breach, however small.
2. **When:** within 5 working days of the incident's end.
3. **Where:** copy everything below the line into a new file in `docs/reports/`, named by the date the incident began and a few words, for example 2026-12-01-postmortem-login-codes-delayed.md. Keep every heading, in this order, even when its answer is "none".
4. **Blameless:** no person is named as a cause. Write what the system, the process or the information let happen, and why it made sense to the person at the time. People are named only as who did a step in the timeline, and who owns an action.
5. **No personal data:** no user's name, phone number, UPI ID or account id. Count the people affected; never list them.
6. **Closed only when reviewed:** the founder who did not write it reads it, questions it, and signs the review section. Until then its status is *Draft*.
7. **Every action is an item:** each one gets a number in `docs/BACKEND_COMPLETE.md` (or `docs/FRONTEND_COMPLETE.md`) and a due date. A fix for a cause is due within **4 weeks** of the review, any other action within **8**. A fix comes with a test that fails without it (`docs/standards/testing.md` section 2).

---

# Postmortem: <a short title, saying what people saw>

**Status:** Draft | Reviewed
**Incident:** <date and time it began, Tamil Nadu time> to <date and time it ended>
**Trigger:** <which of the triggers above>
**Written by:** <founder>, <date>
**The incident log:** <the private GitHub security advisory, if one was opened>

## Summary

Three sentences at most: what happened, to whom, how it ended.

## Impact

In numbers: minutes of downtime or degradation; requests failed; people affected (brands, creators); error budget spent, as a share of the month's, per journey; data lost or exposed, and of what kind. If personal data may have been reached: when CERT-In was told, and the Board and each person (`docs/INCIDENT_RESPONSE.md` section 5).

## Timeline (Tamil Nadu time)

| Time | What happened, or was done, and by whom |
|---|---|
| | The fault begins |
| | The first alert, or the first person to notice |
| | Acknowledged |
| | The harm stopped |
| | Recovered in full |

Minutes from fault to alert: . From alert to acknowledgement: . From fault to recovery: .

## Contributing causes

Every condition that had to be true for this to happen, not one root cause. For each, why it was true.

## What went well

## Where we were lucky

What could have made it worse, and did not, by chance rather than design.

## Actions

| Action | Kind | Item | Due | Owner |
|---|---|---|---|---|
| | Cause fix (4 weeks) / Other (8 weeks) | | YYYY-MM-DD | |

## Review

**Reviewed by:** <the founder who did not write it>, <date>. What the review changed:
