# Relay repository owner handoff

Last reviewed: 2026-07-14

Audience: Abda, repository owner for `KingAbda/Relay`.

Status: **SOURCE RELEASE PREPARATION / NO-GO FOR DEPLOYMENT OR INVITATIONS.**
This page explains how to receive, verify, and maintain the code. It does not
authorize a merge, deployment, database mutation, spend, or participant contact.

## Current GitHub state

As reviewed on 2026-07-14, `KingAbda/Relay` is public, `main` points to
`9fbc1ea`, and there are no open pull requests, open issues, GitHub Actions
workflows, branch rulesets, or readable classic branch protection for `main`.
The release collaborator has push access but not repository admin access.

## What the owner is receiving

The release candidate converts the earlier prototype into an invite-only,
one-category, one-credit controlled-trial system. It adds versioned migrations,
an attributable credit ledger, moderation and consent controls, fail-closed
production configuration, local/CI verification, and operating evidence.

The pre-release GitHub baseline at `9fbc1ea` contains `del_db.py`,
`fix_double_credits.py`, and `migrate_db.py`. Do not run or preserve those
utilities when reconciling the release. They are developer-specific, bypass the
migration/ledger boundaries, and are intentionally replaced by Alembic
migrations plus guarded Flask CLI commands.

## First checkout

Install Git and Python 3.12, then use a normal clone. Do not copy another
developer's `.venv`, `.env`, or SQLite database.

### macOS or Linux

```bash
git clone https://github.com/KingAbda/Relay.git
cd Relay
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m flask --app app.main db upgrade
python -m flask --app app.main run --port 8000
```

### Windows PowerShell

```powershell
git clone https://github.com/KingAbda/Relay.git
Set-Location Relay
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m flask --app app.main db upgrade
python -m flask --app app.main run --port 8000
```

Open <http://localhost:8000>. The default development configuration uses an
ignored SQLite database and in-memory email delivery. A first local run does not
need production credentials.

If PowerShell blocks environment activation, use the virtual environment's
Python directly: `.venv\Scripts\python.exe -m flask --app app.main db upgrade`.
Do not loosen the machine-wide execution policy just for Relay.

## Verify a checkout

With the virtual environment active, run:

```bash
python -W error::DeprecationWarning -m unittest discover -v
python -m compileall -q app migrations scripts tests
python -m pip check
python scripts/check_secret_patterns.py
python scripts/check_release_scope.py
python scripts/check_readiness_artifacts.py
python -m pip_audit --requirement requirements.txt --progress-spinner off
git diff --check
```

The ordinary suite currently contains 62 tests. GitHub Actions additionally
starts disposable PostgreSQL and Redis services for migration, concurrency,
shared-rate-limit, proxy, and production-shaped readiness checks.

## Review and merge this release

1. Require the release branch to contain the latest `origin/main` in its
   history. Resolve the existing remote utility commit by retaining the removed
   campaign behavior but deleting the three unsafe root database utilities.
2. Open a pull request into `main`; do not push this release directly to
   `main`.
3. Read `docs/RELEASE_SCOPE.md`, then inspect the PR's changed-file list. It
   must not contain `.env`, a database/dump, browser logs, local promo sources,
   participant data, or the three unsafe utilities.
4. Confirm the `Relay safety gate / test` workflow is green for the exact PR
   head. A missing or skipped workflow is not a pass.
5. Review the responsive screenshots and either attest the hero poster's
   publication rights in `docs/OWNER_DECISION_PACKET.md` or replace it and
   rerun the evidence.
6. Merge only after the branch is current, checks pass, review conversations
   are resolved, and the intended scope is understood. Keep deployment and
   participant invitations separate.
7. After merge, verify a fresh owner checkout using the commands above and run
   `python -m flask --app app.main db current` to confirm revision
   `20260713_01`.

## GitHub settings only the owner can finish

The current release collaborator can push but does not have repository admin
permission. Abda should configure a `main` branch ruleset that:

- requires a pull request instead of direct pushes;
- requires the `test` status check from the Relay safety-gate workflow;
- requires the branch to be current before merge;
- requires conversations to be resolved; and
- blocks force-pushes and branch deletion.

`.github/CODEOWNERS` identifies `@KingAbda` as the final review owner. Enable
Code Owner review only if another trusted collaborator will be available to
approve owner-authored pull requests; otherwise that setting can deadlock a
single-owner repository.

## Normal owner workflow after merge

```bash
git switch main
git pull --ff-only origin main
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m flask --app app.main db upgrade
python -W error::DeprecationWarning -m unittest discover -v
```

Review dependency changes before installing them. Never run a database repair
script received in chat or committed ad hoc. Schema changes belong in Alembic;
credit corrections belong in attributable, repeat-safe ledger operations.

## What remains an owner decision

The code being mergeable does not make the trial launchable. Abda must complete
`docs/OWNER_DECISION_PACKET.md`, including:

- poster rights or replacement;
- staging provider and spending approval;
- recoverable PostgreSQL, Redis, SMTP, monitoring, and alert destinations;
- named moderation, technical, privacy, support, backup, and rollback owners;
- legal/privacy review; and
- a production-like two-user/operator rehearsal with backup restoration.

Until every launch gate in `docs/TRIAL_READINESS_MATRIX.md` is `PASS`, keep
automatic deploys off and do not invite participants.

`RELAY_BUSINESS_PLAN.md`, `RELAY_DOC.md`, and the older
`RELAY_BUSINESS_PLAN.pdf` are historical planning material. They include
monetization ideas and unverified claims that are not current product behavior,
launch evidence, or owner instructions.
