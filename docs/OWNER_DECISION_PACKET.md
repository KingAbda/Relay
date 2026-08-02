# Relay controlled-trial owner decision packet

Last updated: 2026-08-02

Status: **UNAPPROVED / NO-GO.** Blank fields are intentional. This packet
collects decisions that cannot be made by repository tests. Filling it out does
not itself authorize a push, deployment, migration, participant contact, or
launch; each external action remains separately approved.

Never place credentials, invite-list addresses, participant data, private inbox
contents, or legal advice in this file.

## 1. Repository publication record

- Reviewed release manifest: `docs/RELEASE_SCOPE.md`
- Published application commit:
  `1132a1497eff38a5d3eed39dff1b4a9958a2982e`
- Exact-candidate CI evidence: `Relay safety gate` run `30608587671` passed
- Candidate state: merged into `main`; automatic deployment remains disabled

The redesigned homepage does not request the already tracked hero poster. Choose
one dormant-media outcome before any future use:

- [ ] Keep the unused poster tracked but disabled; confirm rights before any
      future re-enable.
- [ ] Remove or replace it in a separately reviewed change.

Publication record:

- [x] Candidate merged into `main` and exact-candidate CI passed.
- [x] Deployment, migrations, and invitations remain separate approvals.

Repository owner: Abda  Publication date: 2026-07-31

## 2. Staging provider and spend decision

Review `render.staging.yaml` and `docs/STAGING_PROVISIONING_PLAN.md` before
approval. Record only provider/product names and non-secret decisions here.

| Decision | Approved value | Owner | Status |
|---|---|---|---|
| Staging hosting account/workspace | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| Public domain and DNS registrar account | `[UNASSIGNED]` | Abda | PENDING |
| PostgreSQL plan and recovery tier | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| Redis/Key Value plan | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| SMTP provider and verified sender domain | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| Error/log monitoring destination | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| Uptime and readiness alert destination | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| Backup retention, encryption, RPO, and RTO | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |
| Maximum approved monthly staging spend | `[UNASSIGNED]` | `[UNASSIGNED]` | PENDING |

Provisioning approval: `[UNAPPROVED]`  Approver/date: `[UNASSIGNED]`

## 3. Accountable operations coverage

Assignments must be real people with confirmed access and rehearsal
availability. One person may hold multiple roles only if the backup and
separation-of-authority requirements in the operations runbook still hold.

| Role | Named person | Contact path verified | Coverage confirmed | Rehearsal signed |
|---|---|---|---|---|
| Trial decision-maker | `[UNASSIGNED]` | NO | NO | NO |
| Primary moderator | `[UNASSIGNED]` | NO | NO | NO |
| Backup moderator | `[UNASSIGNED]` | NO | NO | NO |
| Technical operator | `[UNASSIGNED]` | NO | NO | NO |
| Privacy contact | `[UNASSIGNED]` | NO | NO | NO |
| Support inbox owner | `[UNASSIGNED]` | NO | NO | NO |
| Rollback approver | `[UNASSIGNED]` | NO | NO | NO |
| Backup/restore operator | `[UNASSIGNED]` | NO | NO | NO |

Published trial coverage window: `[UNASSIGNED]`

## 4. Legal and privacy review request

The reviewer should receive the current rendered product behavior and these
repository documents:

- versioned Terms, Privacy Policy, Safety, Code of Conduct, and Consent pages;
- `docs/TRIAL_CONTRACT.md` and `docs/TRIAL_OPERATIONS_RUNBOOK.md`;
- `docs/BACKUP_RESTORE_RUNBOOK.md` and the post-trial retention procedure;
- account export, closure, pseudonymization, safety-evidence, and 24-month
  limited audit-record behavior;
- cohort eligibility, age rule, campus/public-location logistics, moderation,
  emergency disclaimer, email, and subprocessors/provider list.

Required recorded outcomes:

- [ ] Approved policy text and version identifiers.
- [ ] Approved eligibility and age handling.
- [ ] Approved consent and safety disclosures.
- [ ] Approved data inventory, purposes, access controls, retention, deletion,
      backups, subprocessors, and incident process.
- [ ] Approved privacy-request identity-verification procedure.
- [ ] Any required institutional or university approval is identified and
      obtained, or explicitly determined not required by the qualified reviewer.

Legal reviewer: `[UNASSIGNED]`  Status/date: `[UNREVIEWED]`

Privacy reviewer: `[UNASSIGNED]`  Status/date: `[UNREVIEWED]`

This packet is an engineering handoff, not legal advice.

## 5. Evidence required before invitation approval

All rows must point to redacted staging evidence and a specific reviewed commit.

- [ ] Green GitHub Actions for the exact release commit.
- [ ] Fresh PostgreSQL migration, current-revision check, application boot, and
      readiness success with live Redis.
- [ ] Real signup, verification, password-reset, reminder, and failure/retry
      inbox evidence without tokens or message bodies in logs.
- [ ] Deployed proxy/NAT rate-limit and spoof-resistance evidence.
- [ ] Two-participant booking, cancellation, completion, no-show, dispute,
      moderation, export, and closure rehearsal.
- [ ] Alert delivery and on-call acknowledgement exercise.
- [ ] Provider backup or approved encrypted backup restored into an isolated
      target with readiness, representative journeys, and ledger reconciliation.
- [ ] Primary and backup coverage plus legal/privacy approvals above.
- [ ] Final readiness matrix contains no `FAIL`, `BLOCKED`, or `NOT TESTED`
      launch gate.

Final invitation approval: `[UNAPPROVED]`

Decision-maker/date: `[UNASSIGNED]`
