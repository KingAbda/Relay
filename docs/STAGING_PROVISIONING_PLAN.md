# Relay production-like staging provisioning plan

Last reviewed: 2026-07-14

Status: **DRAFT / NOT PROVISIONED.** The repository now contains a proposed
`render.staging.yaml`; syncing it creates paid resources and is an external
action requiring owner approval. This plan never authorizes a production
deployment or participant invitation.

## Proposed isolated staging stack

All resources use Render's Ohio region and private datastore ingress:

- `relay-staging`: Starter web service, manual deploys only, exact-head
  `/health/ready` check.
- `relay-staging-db`: PostgreSQL 16 on `basic-256mb`, private ingress, no
  connection pool.
- `relay-staging-cache`: Starter Key Value service with `noeviction`; data
  persistence is off because rate-limit counters are loss-tolerant.
- `relay-staging-expired-requests`: authenticated 15-minute cron settlement.
- `relay-staging-session-reminders`: authenticated hourly reminder cron.

The blueprint uses Render property references for database and Key Value URLs.
Relay normalizes provider-issued `postgresql://` URLs to the installed Psycopg 3
dialect and tests that behavior.

Official references:

- [Blueprint schema](https://render.com/docs/blueprint-spec)
- [Health checks](https://render.com/docs/health-checks)
- [Notifications](https://render.com/docs/notifications)
- [Render Key Value](https://render.com/docs/key-value)

## Decisions required before sync

Record each decision without placing credentials or cohort addresses in Git:

| Decision | Required evidence | Status |
|---|---|---|
| Resource spend | Owner approves the current web, two cron, Key Value, and PostgreSQL plans | PENDING |
| Blueprint target | Owner confirms the Render workspace, repository, release branch, and staging-only environment | PENDING |
| SMTP provider | Approved sender domain, SMTP host/port/account, from address, retry expectations, and monitored delivery failures | PENDING |
| Synthetic cohort | 10–20 approved NYU-controlled staging inboxes; addresses remain secret | PENDING |
| Public origin | Exact HTTPS hostname and matching trusted-host value | PENDING |
| Proxy topology | Confirm Render's forwarded-header chain before retaining the proposed X-For/X-Proto hop counts of 1 | PENDING |
| Support address | Monitored non-personal inbox approved for staging messages | PENDING |
| Notifications | Email and/or Slack destination receives deploy, unhealthy-service, and cron-failure alerts | PENDING |
| Recovery objectives | Backup owner, encrypted destination, 24-hour RPO and 2-hour RTO accepted or replaced | PENDING |

Stop if the owner does not approve spend, the staging account would contain real
participant data, the sender domain is unverified, or the service/region names
would collide with existing resources.

## Controlled provisioning sequence

1. Confirm the local release commit and green CI. Record the commit SHA and
   Alembic head; do not deploy a dirty worktree.
2. Validate `render.staging.yaml` against Render's current Blueprint schema.
3. Obtain explicit approval to create the proposed paid resources, then sync
   the staging blueprint with automatic deploys off.
4. Supply all `sync: false` values through Render's secret UI. Use a strong
   generated secret, synthetic inbox allowlist, exact HTTPS origin/trusted host,
   SMTP credentials, and monitored support address.
5. Configure workspace/service notifications for failures. Trigger and retain a
   redacted test notification before counting alerts as working.
6. From an approved one-off staging job or shell, run `flask --app app.main db
   upgrade`, `db current`, and `db check`. Do not make migration automatic until
   rollback compatibility is independently approved.
7. Manually deploy the recorded release commit. Require liveness and exact-head
   readiness, then run read-only `reconcile-credits` and `trial-health-report`.
8. Execute `TRIAL_REHEARSAL_CHECKLIST.md`, including real inbox delivery,
   deployed proxy/NAT limits, two-participant logistics, scheduler results,
   alerts, account recovery, and moderation.
9. Verify provider backup availability, then perform the approved encrypted
   backup and isolated restore procedure in `BACKUP_RESTORE_RUNBOOK.md`.
10. Retain only redacted evidence. Never store credentials, reset/verification
    secrets, connection URLs, cohort addresses, message bodies, or participant
    data in Git, CI artifacts, chat, or tickets.

## Evidence required to close staging gates

Provisioning alone proves nothing. The handoff must include:

- exact release commit, CI run, deployed revision, and Alembic head;
- readiness/liveness results and database/Key Value connectivity;
- redacted successful and failed SMTP outcomes plus sender-domain checks;
- deployed rightmost-proxy and shared-campus-NAT rate-limit results;
- successful cron runs and delivered failure alert;
- provider backup identifier, encrypted backup checksum, isolated restore row
  counts, readiness, login/reset/session checks, and reconciliation;
- completed two-participant and moderator rehearsal rows; and
- named technical, privacy, moderation, decision, and rollback owners.

Until every applicable launch gate is evidenced, staging remains a test system
and Relay remains NO-GO for participant invitations.
