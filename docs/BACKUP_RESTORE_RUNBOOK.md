# PostgreSQL backup, restore, and rollback runbook

Last updated: 2026-07-13

Status: **BLOCKED / LOCAL SYNTHETIC DRILL EXECUTED**. The production provider, encrypted backup location, recovery objectives, and accountable operator are unassigned. A disposable local logical drill passed on 2026-07-13, but it does not satisfy G06. Commands below are a controlled template and do not authorize database access or mutation.

## Required decisions

- Approved recoverable PostgreSQL plan: `[UNASSIGNED]`
- Backup owner and restore operator: `[UNASSIGNED]`
- Encrypted backup destination and access policy: `[UNASSIGNED]`
- Recovery point objective: proposed 24 hours, `[NOT APPROVED]`
- Recovery time objective: proposed 2 hours, `[NOT APPROVED]`
- Retention: daily backups for 30 days, `[NOT APPROVED]`
- Restore-drill cadence: before each invitation wave and monthly during the trial, `[NOT APPROVED]`

## Backup evidence

Using provider-native backups is preferred. If a logical backup is approved, the operator obtains credentials through the secret manager and writes only to the approved encrypted destination. Never place credentials, participant data, or dumps in the repository, shell history, `/tmp`, CI artifacts, chat, or tickets.

Record provider backup ID, database/schema revision, UTC start/end, encrypted-object checksum, size, operator, and redacted log location. Do not record the connection string.

### Local synthetic drill evidence (not launch proof)

On 2026-07-13, a new loopback-only PostgreSQL 16.14 cluster was initialized under `.hermes`; synthetic rehearsal data in `relay_readiness_ci` was dumped with custom format, no owner, and no privileges. The 48,467-byte dump had SHA-256 `3196b09ab0fef7cc0acb7712383ec7b14c447e1d2f586f31feaee37a765e6984` and restored with `--exit-on-error` into new isolated `relay_restore_ci`.

The restored database was at exact Alembic head `20260713_01`, contained the expected aggregate synthetic counts (2 users, 1 skill, 2 accounts, 2 transactions), passed `flask db check`, returned application readiness in test mode, and reconciled with zero discrepancies. No real credential, participant data, provider backup, encrypted destination, approved RPO/RTO, alert, login/reset journey, two-user settlement, or operator sign-off was involved. The disposable cluster and dump were removed after verification, so G06 remains **BLOCKED**.

## Isolated restore drill

1. Freeze the staging rehearsal dataset and record aggregate source counts plus `flask reconcile-credits` output.
2. Create an empty, isolated restore target with no public ingress and least-privilege credentials.
3. Restore the selected backup using the provider's supported method or `pg_restore` only after explicit approval.
4. Point the matching application revision at the isolated target and run migration status without applying unreviewed changes.
5. Verify `/health/ready`, schema revision, aggregate row counts, representative login/reset, two-user session settlement, moderator access, account export/deletion, and full ledger reconciliation.
6. Record elapsed time and compare with approved RTO/RPO. Destroy the isolated target only after the evidence owner confirms capture; destruction is a separate destructive action requiring approval.

## Incident restore decision

The rollback approver chooses one of: application rollback with unchanged compatible schema; forward fix; point-in-time database restore; or continued outage. Before a restore, stop writes, preserve logs/request IDs, record the incident cutoff, and identify transactions that may be replayed. After restore, rotate exposed credentials, run readiness and reconciliation, and reopen only after moderator and technical sign-off.

Never restore over the sole production database, run an untested downgrade, or combine a data restore with speculative ledger repair. Until a real restore transcript passes, G06 remains **BLOCKED**.
