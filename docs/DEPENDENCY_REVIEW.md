# Relay dependency security review

Last updated: 2026-07-23

Status: **PASS locally; committed base CI passed; exact local candidate awaits CI**.

All runtime requirements are exact direct pins. The security updates and newly
authorized operational dependencies are:

| Dependency | Exact pin | Compatibility / advisory evidence |
|---|---:|---|
| Flask | 3.1.3 | Patched release; current PyPI release metadata returned no advisories. |
| Werkzeug | 3.1.8 | Patched release compatible with Flask 3.1.3; current metadata returned no advisories. |
| Flask-Migrate | 4.1.0 | Supports Flask-SQLAlchemy and Alembic; migration CLI and tests pass. |
| Alembic | 1.18.5 | Supports SQLAlchemy 2.0.50 and Python 3.12; SQLite migration/drift tests pass. |
| psycopg with binary extra | 3.3.4 | Imports on Python 3.12; guarded migrations and concurrency pass on disposable PostgreSQL 16.14. |
| redis | 8.0.1 | Imports with Flask-Limiter; two application instances share counters through disposable Redis 7.4.9, and production-shaped readiness passes with that store. |
| pip-audit | 2.10.1 | Pinned in `requirements-dev.txt`; scans the resolved runtime graph locally and in CI. |

Primary package metadata: [Flask](https://pypi.org/project/Flask/),
[Werkzeug](https://pypi.org/project/Werkzeug/),
[Flask-Migrate](https://pypi.org/project/Flask-Migrate/),
[Alembic](https://pypi.org/project/alembic/),
[psycopg](https://pypi.org/project/psycopg/),
[redis](https://pypi.org/project/redis/), and
[pip-audit](https://pypi.org/project/pip-audit/).

## Verification

```text
.venv/bin/python -m pip check
# No broken requirements found.

.venv/bin/python scripts/check_direct_advisories.py
# direct advisory check passed for 14 exact pins

.venv/bin/python -m pip_audit --progress-spinner off
# No known vulnerabilities found

.venv/bin/python -W error::DeprecationWarning -m unittest discover -v
# 62 tests passed
```

The direct check fails closed if PyPI release metadata is unavailable. `pip-audit`
checks the resolved runtime dependency graph against published vulnerability data.
Neither result proves future safety, package provenance, licenses, or reproducible
hashes. The `Relay safety gate` repeated the checks successfully for committed
base `8c775556`. The exact local redesign/edge-case candidate is saved in one
local commit, so it requires a new CI run after an owner-approved push. No dependency
or lockfile changed in this candidate.

## Release rule

Do not invite participants if either advisory check fails, dependency resolution is
inconsistent, or production-like PostgreSQL/Redis behavior has not passed. Security
updates must remain exact-pinned, reviewed, warning-strict tested, and paired with
the matching application and migration revisions.
