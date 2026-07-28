# Relay repository owner handoff

Last reviewed: 2026-07-23

Audience: Abda, repository owner for `KingAbda/Relay`.

Status: **READY FOR OWNER CODE REVIEW / NO-GO FOR DEPLOYMENT OR INVITATIONS.**

## Where the project is now

The committed `main` branch and `origin/main` are synchronized at
`8c775556ae19540089058d4748e001816814855a`. GitHub Actions passed on that exact
committed base. The calm-dark redesign, two operational fixes, regression
coverage, and current readiness documents are saved together in one
owner-approved local commit on top of that base.

The local candidate now:

- removes the blocked Google Font request and uses system fallbacks;
- keeps the calm-dark direction while passing mobile, desktop, keyboard, focus,
  reduced-motion, static-mode, and contrast checks;
- makes Redis readiness exceptions return a clean `503 not_ready`;
- tells the deleting user when session-cancellation emails fail while still
  completing the account closure;
- passes all 62 ordinary tests and five guarded PostgreSQL migration/concurrency
  tests;
- passes the guarded shared-Redis/trusted-proxy test and production-shaped
  PostgreSQL/Redis readiness at exact migration head;
- passes compile, secret, dependency, advisory, source-scope, YAML, whitespace,
  and untracked-file checks; and
- excludes `Relay Backend Architecture.tldraw` from release scope without
  deleting the owner's local file.

The exact candidate has not been pushed, so it has not had its own GitHub
Actions run. No staging environment exists.

## Owner action 1: review the local candidate commit

Review `docs/RELEASE_SCOPE.md`, the complete commit diff, and
`git diff-tree --no-commit-id --name-only -r HEAD`. The
clean-tree/source-boundary command passes:

```bash
python scripts/check_release_scope.py --require-clean --require-origin-main-base
```

## Owner action 2: authorize publication for review

Separately authorize a release branch push and pull request. Require the `Relay
safety gate / test` check to pass for the exact candidate commit before merge.
Do not treat the green base-commit run as candidate evidence.

GitHub still needs owner/admin configuration:

- require pull requests for `main`;
- require the `test` check and an up-to-date branch;
- require resolved review conversations;
- block force-pushes and branch deletion; and
- enable dependency-alert visibility if the owner accepts that repository
  setting.

## Owner action 3: choose and fund staging

Complete `docs/OWNER_DECISION_PACKET.md`: hosting account, recoverable
PostgreSQL, Redis, real SMTP and sender domain, authenticated scheduler,
central logs/error reporting, uptime/readiness alerts, backup retention and
recovery targets, and the maximum monthly staging spend.

Provisioning or deploying those resources is a separate external action and is
not authorized by the code review.

## Owner action 4: name people and obtain approvals

Assign real people for trial decisions, primary and backup moderation,
technical operation, support inbox, privacy requests, rollback, and
backup/restore. Obtain qualified legal/privacy review of the rendered policies,
consent, eligibility, retention, deletion, safety, and provider disclosures.

## Owner action 5: run the staging rehearsal

On the exact reviewed commit, prove:

- migrations, exact database revision, production boot, Redis-backed readiness,
  and the deployed proxy/NAT boundary;
- real signup, verification, password reset, reminders, cancellation, and
  delivery-failure handling through the real email provider;
- two-participant booking, cancellation, completion, no-show, dispute,
  moderation, export, and deletion;
- alert delivery and operator acknowledgement; and
- a provider/encrypted backup restored into an isolated target with readiness
  and ledger reconciliation.

Only after every launch gate is `PASS` should the owner separately approve
production deployment and participant invitations.

## Normal verification

```bash
python -W error::DeprecationWarning -m unittest discover -v
python -m compileall -q app migrations scripts tests
python -m pip check
python -m pip_audit --progress-spinner off
python scripts/check_secret_patterns.py
python scripts/check_release_scope.py
python scripts/check_readiness_artifacts.py
python scripts/check_direct_advisories.py
git diff --check
```

The ordinary suite contains 62 tests. GitHub Actions additionally starts
disposable PostgreSQL and Redis services for migrations, concurrency,
shared-rate-limit/proxy, and production-shaped readiness checks.
