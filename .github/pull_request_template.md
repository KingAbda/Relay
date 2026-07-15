## What changed

Describe the customer-visible outcome and the reason for the change.

## Verification

- [ ] `python -W error::DeprecationWarning -m unittest discover -v`
- [ ] `python -m compileall -q app migrations scripts tests`
- [ ] `python -m pip check`
- [ ] `python scripts/check_secret_patterns.py`
- [ ] `python scripts/check_release_scope.py`
- [ ] `python scripts/check_readiness_artifacts.py`
- [ ] `git diff --check`
- [ ] UI changes were checked at desktop and mobile widths.

## Release safety

- [ ] This branch is based on the latest `origin/main`.
- [ ] No `.env`, credentials, participant data, databases, dumps, browser logs, or local media sources are included.
- [ ] Schema changes use Alembic migrations; no one-off database mutation script is included.
- [ ] Deployment, migration, spend, and participant-contact actions remain separately approved.
- [ ] The current NO-GO launch status is unchanged unless every readiness gate has evidence.

## Owner decision

- [ ] Abda reviewed the changed files and GitHub Actions result.
- [ ] Any required media, legal, privacy, operations, or spend decision is recorded in `docs/OWNER_DECISION_PACKET.md`.
