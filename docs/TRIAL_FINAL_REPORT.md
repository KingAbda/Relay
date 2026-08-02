# Relay controlled-trial engineering report

Last updated: 2026-08-02

## Verdict

**NO-GO.** The reviewed application candidate is merged into `main` at `1132a149` and passed the full GitHub Actions safety gate, including application, dependency, PostgreSQL migration/concurrency, Redis/proxy, and production-shaped readiness checks. Four launch gates remain blocked and three remain not tested because no production-like staging, real email, provider recovery, deployed proxy/NAT, legal review, or named operations coverage exists. No invitations, deployment, persistent-database migration, or real participant data should be authorized from this evidence.

The authoritative inventory remains `TRIAL_READINESS_MATRIX.md`:

- Audit issues: 45 PASS, 0 FAIL, 5 BLOCKED, 0 NOT TESTED (50 total).
- Launch gates: 5 PASS, 0 FAIL, 4 BLOCKED, 3 NOT TESTED (12 total).
- Per-ID implementation and test locators: `TRIAL_EVIDENCE_INDEX.md`.

## Repository-controlled outcome

Implemented and locally exercised:

- Invite-only NYU contract validation for 10–20 unique approved-domain addresses, one configurable creative vertical, one credit per 30 minutes, bounded starter credits, strong production secrets, canonical HTTPS/trusted-host requirements, explicit trusted-proxy hop counts, PostgreSQL-only production URL with provider-issued URLs normalized to Psycopg 3, Redis-only production limiter storage, and SMTP-only production email.
- Integer source-unique ledger, nonnegative database constraints, locked state mutations, strict session state machine, source-settlement validation for refunds/payouts/reversals, cross-case reversal idempotency, dispute-state restoration/closure, reconciliation behavior, and repeat-safe reviews and delivery records.
- Hashed expiring verification/reset secrets, hashed login-identity throttling, account-scoped sensitive-mutation limits that avoid sharing allowances across campus users, session versioning, non-active login rejection, reset-link revocation on reset/suspension/closure, versioned consent, verified-only identity access, public-description suppression, comprehensive account export, and truthful pseudonymized closure/retention behavior.
- DST gap/fold rejection, one-hour–30-day Eastern schedule bounds, participant-visible schedule before acceptance, exact approved public locations/HTTPS hosts, participant-only details, cancellation/no-show/dispute/block/report/suspension/moderation flows, mandatory action reasons/evidence, and attributable ledger correction.
- Secret-free delivery outcomes for verification, reset and session lifecycle messages; authenticated dry-run-first expiry settlement and reminders; non-zero scheduler results on provider failure; canonical links from CLI and HTTP contexts.
- Dry-run-first synthetic rehearsal fixture restricted to test/staging and guarded by explicit authorization; reserved `.invalid` identities and source-unique starter events.
- Separate liveness/readiness with exact Alembic-head and shared-limiter enforcement, bounded Redis timeouts, no-store responses, request IDs, structured request/error events, aggregate PII-free trial metrics, and fail-closed Render configuration with no database provisioning or automatic deployment.
- Patched Flask/Werkzeug pins, exact PostgreSQL/Redis/migration dependencies, a pinned local pip-audit scanner, clean 14-pin PyPI advisory results, a clean resolved-runtime scan, and dependency consistency.
- Flask-Migrate/Alembic legacy baseline and adoption revisions with independent representative data; fresh/no-drift, upgrade/rollback preservation, and preflight refusal are tested on disposable SQLite, while guarded fresh/legacy forward-and-rollback execution passes on disposable PostgreSQL 16.14.
- Rendered public-surface assertions for unique IDs, programmatic control labels, CSRF on every POST form, CSP-compatible scripts/assets, intrinsic image dimensions, trial-claim containment, and basic CSS structural validity; the calm-dark redesign removes the external Google Font request, uses system fallbacks, makes explicit static mode motion-free, and keeps normal-text contrast at or above 4.5:1.
- CI structure for source-only release-scope enforcement, consistency, deployment-blueprint parsing, compile, 88 warning-strict tests, secret patterns, readiness-ledger consistency, direct/resolved advisory scans, disposable PostgreSQL 16 migration/concurrency, Redis 7.4 shared-limit/proxy, and production-shaped infrastructure services.
- Guarded PostgreSQL migration and concurrency modules pass all five tests against the explicitly disposable local `relay_migration_ci` database, including competing holds, completion confirmations, and cancellation/completion behavior with exact reconciliation.
- The exact production import boots against disposable PostgreSQL 16.14 and Redis 7.4.9 after migration/current/check; trusted proxy selection ignores a spoofed leftmost address, the live limiter records the configured rightmost address, and exact-head readiness returns `200`.
- Two independently constructed application instances share the same Redis limit counter, while a different participant address retains an independent allowance; all guarded infrastructure tests flush Redis database 15 and destroy the disposable PostgreSQL schema afterward.
- A synthetic `pg_dump`/`pg_restore` drill restores exact Alembic head, aggregate row counts, application readiness in test mode, and zero ledger discrepancies into an isolated restore database. This does not satisfy the real encrypted/provider recovery gate.
- Fresh isolated headless Chrome passes 375/500/768/1440 screenshots, a 200% reflow approximation, keyboard/focus/skip-link, menu, reduced-motion and explicit static modes, labels, unique IDs/H1s, strict CSP/same-origin assets, request/console errors, intrinsic images, full reveal settling, and AA palette contrast checks.

Intentionally disabled behavior and re-enable conditions are in `DISABLED_FEATURES.md`. Operational, release, moderation, privacy, recovery and rollback procedures are in `TRIAL_OPERATIONS_RUNBOOK.md` and `BACKUP_RESTORE_RUNBOOK.md`.

## Exact local verification

Passing evidence:

```text
.venv/bin/python -W error::DeprecationWarning -m unittest discover -v
# Ran 88 tests — OK

RELAY_TEST_POSTGRES_URL=postgresql+psycopg://relay@127.0.0.1:55433/relay_owner_ready_ci \
RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest \
    tests.postgres_migrations tests.postgres_concurrency -v
# Ran 5 tests — OK

RELAY_TEST_REDIS_URL=redis://127.0.0.1:56379/15 \
RELAY_REDIS_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest tests.redis_proxy -v
# Ran 1 test — OK

RELAY_TEST_POSTGRES_URL=postgresql+psycopg://relay@127.0.0.1:55432/relay_migration_ci \
RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true \
RELAY_TEST_REDIS_URL=redis://127.0.0.1:56379/15 \
RELAY_REDIS_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest tests.production_infrastructure -v
# Ran 1 test — OK; exact-head production-shaped readiness returned 200

# Production-shaped boot against isolated PostgreSQL 16.14 and Redis 7.4.9
# /health/ready -> 200; live limiter uses the configured rightmost proxy IP;
# db current/check -> exact 20260731_01 head/no drift

# Synthetic custom-format pg_dump/pg_restore into relay_restore_ci
# exact head, 2 users, 1 skill, 2 accounts, 2 transactions,
# ready in test mode, reconciliation discrepancies 0

# Fresh isolated headless Chrome 149 / bundled Playwright
# 375/500/768/1440 + 200% reflow, ten public routes, keyboard/focus,
# reduced/static motion, CSP/network, screenshots, contrast -> PASS

.venv/bin/python -m unittest tests.test_migrations -v
# Ran 5 tests — OK

.venv/bin/python -m compileall -q app migrations scripts tests
# exit 0

.venv/bin/python -m pip check
# No broken requirements found

.venv/bin/python -m pip_audit --progress-spinner off
# No known vulnerabilities found

.venv/bin/python scripts/check_direct_advisories.py
# direct advisory check passed for 14 exact pins

.venv/bin/python scripts/check_secret_patterns.py
# secret pattern check passed

.venv/bin/python scripts/check_readiness_artifacts.py
# readiness artifact check passed: 50 issues and 12 gates aligned across the matrix, evidence index, final report, and HTML audit

ruby -e 'require "yaml"; YAML.load_file("render.yaml"); YAML.load_file(".github/workflows/ci.yml"); puts "yaml ok"'
# yaml ok

git diff --check
# exit 0
```

Inventory integrity:

```text
# scripts/check_readiness_artifacts.py fails closed unless the readiness matrix,
# evidence index, final report status totals, and HTML audit agree on all
# 50 issue IDs/statuses and all 12 gate IDs/statuses.
```

## Evidence not claimed

The following were not run and are not treated as passing:

- Successful full readiness in a real staging environment. Production-shaped local PostgreSQL/Redis readiness passed, but no real SMTP/provider was used.
- Real deployed-proxy and shared-campus-NAT behavior, dependency license policy, or reproducible requirement hashes.
- Real provider/inbox delivery, sender-domain authentication, retry, bounce, or alert evidence.
- Real encrypted/provider backup and operator-signed isolated restore. Only a synthetic local logical drill passed.
- Render staging/production deployment, uptime/error alert delivery, or authenticated scheduler provisioning. Exact-candidate GitHub CI passed.
- Official Chrome DevTools performance tracing, field/Core Web Vitals, or human screen-reader review. Browser-backed width, keyboard/focus, 200% reflow approximation, reduced/static motion, CSP/network, screenshot, and contrast evidence did run.
- Counsel/privacy approval, named operators, monitored support inbox, coverage rehearsal, or founder release approval.

## Required next actions

1. Owner chooses and funds production-like staging with recoverable PostgreSQL, Redis, real SMTP, scheduler, log/error and uptime alert destinations.
2. Engineering provisions the approved staging stack and executes the full readiness, deployed-proxy/NAT, rehearsal, and real encrypted/provider restore checklists.
3. Owner assigns and rehearses primary/backup moderator, technical operator, privacy contact, support inbox, decision-maker and rollback approver, and obtains external legal/privacy review.
4. Only after all 12 gates pass: owner separately approves production deployment and participant invitations.

## Repository state boundary

No dependency or lockfile changed in the reviewed candidate. The 2026-07-23 local run used isolated disposable PostgreSQL and Redis resources only. GitHub Actions run `30608587671` repeated the complete safety gate on merged application commit `1132a1497eff38a5d3eed39dff1b4a9958a2982e` and passed. No staging or production database, SMTP provider, participant data, deployment, invitation, or credential was touched by that verification.
