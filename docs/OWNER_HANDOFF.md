# Relay repository owner handoff

Last reviewed: 2026-08-02

Audience: Abda, repository owner for `KingAbda/Relay`.

Status: **CODE MERGED AND CI GREEN / NO-GO FOR DEPLOYMENT OR INVITATIONS.**

## Where the project is now

The reviewed application candidate is merged into `main` at
`1132a1497eff38a5d3eed39dff1b4a9958a2982e`. GitHub Actions run `30608587671`
passed on that exact commit. Automatic deployment remains disabled and no
staging environment exists.

The published candidate:

- removes the blocked Google Font request and uses system fallbacks;
- keeps the calm-dark direction while passing mobile, desktop, keyboard, focus,
  reduced-motion, static-mode, and contrast checks;
- makes Redis readiness exceptions return a clean `503 not_ready`;
- tells the deleting user when session-cancellation emails fail while still
  completing the account closure;
- passes all 88 ordinary tests and five guarded PostgreSQL migration/concurrency
  tests;
- passes the guarded shared-Redis/trusted-proxy test and production-shaped
  PostgreSQL/Redis readiness at exact migration head;
- passes compile, secret, dependency, advisory, source-scope, YAML, whitespace,
  and untracked-file checks; and
- excludes `Relay Backend Architecture.tldraw` from release scope without
  deleting the owner's local file.

## Owner action 1: maintain GitHub safeguards

GitHub still needs owner/admin configuration:

- require pull requests for `main`;
- require the `test` check and an up-to-date branch;
- require resolved review conversations;
- block force-pushes and branch deletion; and
- enable dependency-alert visibility if the owner accepts that repository
  setting.

## Owner action 2: purchase the domain and fund staging

Purchase the public domain in an owner-controlled registrar account with 2FA
and auto-renewal, then grant engineering DNS access. Complete
`docs/OWNER_DECISION_PACKET.md`: hosting account, recoverable
PostgreSQL, Redis, real SMTP and sender domain, authenticated scheduler,
central logs/error reporting, uptime/readiness alerts, backup retention and
recovery targets, and the maximum monthly staging spend.

Provisioning or deploying those resources is a separate external action and is
not authorized by the code review.

## Owner action 3: name people and obtain approvals

Assign real people for trial decisions, primary and backup moderation,
technical operation, support inbox, privacy requests, rollback, and
backup/restore. Obtain qualified legal/privacy review of the rendered policies,
consent, eligibility, retention, deletion, safety, and provider disclosures.

## Engineering action after owner approval: run the staging rehearsal

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

The ordinary suite contains 88 tests. GitHub Actions additionally starts
disposable PostgreSQL and Redis services for migrations, concurrency,
shared-rate-limit/proxy, and production-shaped readiness checks.
