# Relay controlled-trial operations runbook

Last updated: 2026-07-13

Status: **DRAFT / NO-GO**. Bracketed assignments must be completed, rehearsed, and approved before invitations are sent. This document describes actions; it does not authorize a deployment, database mutation, participant contact, or credential change.

## Accountable roles and response targets

| Role | Named owner | Coverage / target | Current gate |
|---|---|---|---|
| Trial decision-maker | `[UNASSIGNED]` | May pause or end the trial at any time | BLOCKED |
| Primary moderator | `[UNASSIGNED]` | Review urgent safety reports within 30 minutes during published trial hours | BLOCKED |
| Backup moderator | `[UNASSIGNED]` | Takes over after a 10-minute acknowledgement miss | BLOCKED |
| Technical operator | `[UNASSIGNED]` | Acknowledge access, email, or ledger incidents within 30 minutes | BLOCKED |
| Privacy contact | `[UNASSIGNED]` | Respond to data requests within 5 business days | BLOCKED |
| Support channel | `RELAY_CONTACT_EMAIL` / `[UNCONFIRMED INBOX]` | Published only after inbox monitoring is proven | BLOCKED |
| Rollback approver | `[UNASSIGNED]` | Sole authority for production rollback/restore | BLOCKED |

The trial must run only during hours in which the primary or backup moderator and technical operator are reachable. Immediate danger is directed to emergency services or campus safety; Relay is not an emergency service.

## Before each invitation wave

1. Confirm the launch matrix has no `FAIL`, `BLOCKED`, or `NOT TESTED` launch gate.
2. Confirm exactly 10–20 approved NYU addresses are present in the secret invite allowlist; never commit or paste that list into evidence.
3. Confirm the configured category is `creative`, the price is one credit, starter credits are two, and disabled features still return `404`.
4. Verify production readiness, the current migration revision, backup freshness, restore-drill date, email delivery, shared rate-limit storage, and alert delivery.
5. Run the read-only checks and retain redacted output:

   ```text
   flask reconcile-credits
   flask trial-health-report
   ```

6. Complete the rehearsal checklist in `TRIAL_REHEARSAL_CHECKLIST.md` with fresh staging accounts.
7. Have the decision-maker sign and timestamp the invitation-wave record. Sending invitations is a separate external action requiring approval.

## Release and staging rehearsal

1. Identify one reviewed application commit and matching database migration revision. Record both; do not release a dirty worktree or an unreviewed schema pair.
2. Require green CI, dependency/advisory checks, migration upgrade/downgrade evidence, and a recoverable pre-release backup before deployment approval.
3. Keep Render automatic deployment disabled. The rollback approver authorizes one manual staging release, verifies the exact revision, and only later authorizes production.
4. Generate the synthetic baseline only in an approved test/staging database. Preview first:

   ```text
   flask prepare-rehearsal-data
   flask prepare-rehearsal-data --apply
   ```

   Apply requires `RELAY_REHEARSAL_DATA_AUTHORIZED=true` and a strong secret `RELAY_REHEARSAL_PASSWORD`. The command refuses production, uses reserved `.invalid` identities, reports counts without addresses, and is repeat-safe. It deliberately bypasses real verification, so use separately approved real-inbox accounts to prove verification and delivery.
5. Execute every row in `TRIAL_REHEARSAL_CHECKLIST.md`, retain redacted evidence, and stop on any discrepancy. A production release remains a separate approved external action.
6. After release, verify readiness, migration revision, reconciliation, aggregate health, alert delivery, and rollback reachability before invitations. Roll back or keep the service unavailable if any check fails.

Local evidence on 2026-07-13 proved exact-head application readiness `200` against disposable PostgreSQL 16.14 and Redis 7.4.9, shared limits across two app instances, spoof-resistant rightmost proxy selection, and independent participant allowances. Missing-storage regressions still fail closed. Scheduler apply mode refuses an unauthenticated context, and a synthetic logical backup can be restored and reconciled. These are localhost component checks only: they do not substitute for real SMTP, the deployed proxy/NAT topology, alert destinations, provider backup, named operators, or the full staging checklist.

## Participant onboarding and support

1. Add only vetted addresses to the secret allowlist through the approved environment-secret workflow.
2. The participant signs up, affirmatively accepts all five current documents, and receives a 24-hour verification link.
3. Starter credits are granted once, only after successful verification. A participant cannot onboard, view identities, list, book, complete, or receive rewards while unverified.
4. If verification delivery fails, check only the aggregate health report and the participant's secret-free delivery record. Never copy a token or message body into logs or tickets. Ask the participant to use resend only after the five-minute cooldown.
5. For account access, use password reset; never set or ask for a participant password. A successful reset revokes existing sessions.
6. For correction/export/deletion, direct a signed-in participant to Edit Profile. If they cannot sign in, the privacy owner follows the separately approved identity-verification procedure; no ad-hoc disclosure is allowed.

## Session support

- Requests must include an America/New_York time between one hour and 30 days ahead.
- Acceptance requires one approved public campus lobby or an exact-host HTTPS meeting link. Relay never creates a meeting link.
- Both participants use the session-details page. Only both completion confirmations release the one-credit payout.
- Either participant may cancel a requested or confirmed session; the held credit is refunded once.
- A no-show can be reported only after the 15-minute grace period and enters moderation. A completed-session dispute also enters moderation.
- Unaccepted requests may be previewed by the scheduled command. Apply mode is permitted only from the authenticated scheduler context:

  ```text
  flask settle-expired-requests
  flask settle-expired-requests --apply
  ```

  The first command is read-only. The second cancels eligible requests, refunds each hold once, and sends each participant one expiry notification. Settlement remains committed if delivery fails, but the command exits non-zero and retains secret-free failure records. Do not run apply mode manually in production without the rollback approver's authorization.

- Upcoming confirmed sessions use a separate dry-run-first reminder command:

  ```text
  flask send-session-reminders
  flask send-session-reminders --apply
  ```

  The default window is the next 24 hours. Apply mode requires the authenticated scheduler context and sends at most one secret-free reminder per session and participant. A provider failure exits non-zero, preserves session state, and leaves an attributable delivery outcome for operator review.

## Moderation and escalation

| Severity | Examples | Initial action | Target |
|---|---|---|---|
| S0 immediate danger | Credible threat, violence, medical emergency | Tell reporter to contact emergency/campus services; pause implicated account/session; notify decision-maker | Immediate |
| S1 urgent safety/privacy | Harassment, stalking, exposed private data, credible retaliation | Acknowledge, preserve evidence notes, suspend if necessary, stop contact, review affected sessions | 30 minutes in coverage hours |
| S2 integrity/access | Ledger mismatch, account takeover suspicion, bulk email failure | Pause affected action or invitation wave, preserve request IDs, technical review | 30 minutes |
| S3 routine | Scheduling confusion, ordinary cancellation, profile correction | Support response | 1 business day |

Moderator actions require a reason and evidence notes. Dismissal, suspension, listing removal, held-credit refund, and completed-session reversal append an attributable moderation record. Do not delete reports or rewrite ledger rows. A block immediately prevents profile/session continuation and cancels/refunds active interactions.

Stop the whole trial when any of these occurs: ledger discrepancy; unauthorized identity exposure; suspected secret compromise; unhandled S0/S1 report; backup/restore uncertainty; repeated delivery failure preventing safe access; migration drift; or loss of operator coverage. The decision-maker records the time, reason, affected scope, and restart criteria.

## Daily operating rhythm

At opening and closing, retain redacted output from `flask trial-health-report` and `flask reconcile-credits`. Review open reports/disputes and failed delivery counts. Check readiness and alert delivery. Do not export participant-level data for routine metrics.

Success measures are aggregate: invited, verified, onboarded, active listings, requested/confirmed/completed/cancelled/no-show/disputed sessions, open safety cases, failed deliveries, and ledger discrepancies. Counts support operational decisions; they are not a substitute for participant interviews or safety review.

## Database recovery and rollback

Follow `BACKUP_RESTORE_RUNBOOK.md`. A real encrypted backup and isolated restore must succeed before launch. Application rollback must be compatible with the database revision; never deploy old application code across an irreversible schema. If compatibility is uncertain, keep the service unavailable and restore the last jointly verified application/database pair.

Never "repair" a balance by editing the account row. First preserve evidence, stop settlement, run read-only reconciliation, identify the immutable source event, and use only a reviewed versioned migration or an attributable moderation reversal.

## Post-trial closure

1. Stop new invitations, listings, and bookings; communicate closure only after approval.
2. Resolve or hand off every open safety report and dispute.
3. Run final health and ledger reports; investigate any discrepancy before archiving.
4. Provide the approved export/deletion window and support coverage.
5. Record the trial-close timestamp that starts the 24-month limited, pseudonymized audit-record retention period.
6. Remove invite-list secrets, rotate trial-only credentials, disable scheduler/email access, and verify no staging participant data remains.
7. Delete direct identifiers when their approved purpose ends; rotate expired backup copies within 30 days. Retain only the access-restricted pseudonymized records described in the Privacy Policy, recognizing that free-text safety evidence may remain identifying.
8. Archive redacted evidence, decisions, incidents, and lessons learned. Do not retain secret values or message bodies.
