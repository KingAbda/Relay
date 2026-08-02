# Relay — trade skills, not money

Relay is a one-credit campus skill exchange being prepared for a tightly controlled student trial.

## Current status

**NO-GO for deployment or participant invitations.** Local containment,
dependencies, SQLite/PostgreSQL migrations and concurrency, and fresh
responsive/basic-accessibility browser checks pass. The reviewed application
candidate is merged into `main` at `1132a149` and its full GitHub Actions safety
gate passed. Real email, real recovery, deployed proxy/NAT, staging/deployment,
legal review, and named operations ownership remain unresolved.

- [Readiness matrix](docs/TRIAL_READINESS_MATRIX.md) — all 50 audit issues and 12 launch gates
- [Engineering report](docs/TRIAL_FINAL_REPORT.md) — exact commands, results, and remaining actions
- [Trial contract](docs/TRIAL_CONTRACT.md)
- [Operations runbook](docs/TRIAL_OPERATIONS_RUNBOOK.md)
- [Owner handoff](docs/OWNER_HANDOFF.md) — Abda's checkout, review, and merge sequence

## Controlled-trial scope

- 10–20 manually vetted NYU participants, enforced by a secret invite allowlist in production
- Exactly one configured category; the reviewed local default is `creative`
- Exactly one integer credit per 30-minute session
- Two starter credits by default, granted once after successful verification
- Full identities and profiles visible only to verified trial participants
- Agreed approved public location or exact-host HTTPS meeting link; Relay creates no meeting links
- No payments, paid plans, referrals, proof rewards, self-service ambassador role, recurring bookings, public request claiming, or demo top-ups

See [intentionally disabled features](docs/DISABLED_FEATURES.md) for the evidence and re-enable conditions.
`RELAY_BUSINESS_PLAN.md`, `RELAY_DOC.md`, and `RELAY_BUSINESS_PLAN.pdf` are
historical planning artifacts, not current product or launch instructions.

## Local development

Relay uses Python 3.12, pinned for local development, CI, and Render by
`.python-version`. From a fresh clone on macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m flask --app app.main db upgrade
python -m flask --app app.main run --port 8000
```

On Windows PowerShell, create the environment with `py -3.12 -m venv .venv`
and activate it with `.venv\Scripts\Activate.ps1`; the remaining commands are
the same. Open <http://localhost:8000> after the server starts.

Development defaults to a local ignored SQLite database and the in-memory email
backend, so no secrets are required for the first run. Review `.env.example`
before exporting overrides. Run `db upgrade` after every pull that contains a
new migration. Persistent environments never create or upgrade tables at
application startup.

## Verification

```bash
.venv/bin/python -W error::DeprecationWarning -m unittest discover -v
.venv/bin/python -m compileall -q app migrations scripts tests
.venv/bin/python -m pip check
.venv/bin/python -m pip_audit --requirement requirements.txt --progress-spinner off
.venv/bin/python scripts/check_secret_patterns.py
.venv/bin/python scripts/check_release_scope.py
.venv/bin/python scripts/check_direct_advisories.py
.venv/bin/python scripts/check_readiness_artifacts.py
ruby -e 'require "yaml"; YAML.load_file("render.yaml"); YAML.load_file("render.staging.yaml"); YAML.load_file(".github/workflows/ci.yml"); puts "yaml ok"'
git diff --check
```

All listed local checks pass; the warning-strict suite currently runs 88 tests.
The advisory checks require network access and fail closed when published data
cannot be obtained.

SQLite forward/rollback migration tests and guarded disposable PostgreSQL migration/concurrency tests pass. Their exact invocation and the production-shaped local boot boundary are documented in the migration runbook and engineering report.

## Operational commands

These commands are read-only unless `--apply` is given. Apply modes have additional environment guards and do not authorize production mutation by themselves.

```bash
flask --app app.main reconcile-credits
flask --app app.main trial-health-report
flask --app app.main settle-expired-requests
flask --app app.main send-session-reminders
flask --app app.main prepare-rehearsal-data
```

## Stack

- Flask and SQLAlchemy
- SQLite for disposable local tests; psycopg-backed PostgreSQL is mandatory for production
- Flask-Migrate/Alembic versioned migrations and a Redis client for shared rate limits
- Server-rendered HTML, self-hosted CSS/JavaScript/assets
- Flask-WTF CSRF protection, Bleach sanitization, Flask-Limiter, trusted hosts with explicit proxy-hop trust, strict script CSP, no-store responses, and structured request IDs
- Render blueprint with automatic deployment disabled and no database provisioned

## License

MIT
