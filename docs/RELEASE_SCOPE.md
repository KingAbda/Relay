# Relay published controlled-trial scope

Last reviewed: 2026-08-02

Status: **PUBLISHED TO `main` / NO-GO FOR DEPLOYMENT.** This manifest records
the reviewed application candidate now on GitHub. Publication does not authorize
a deployment, paid resource, persistent database migration, participant contact,
or launch.

## Base and branch state

- The reviewed application candidate is merged into `main` at
  `1132a1497eff38a5d3eed39dff1b4a9958a2982e`.
- The exact commit passed the `Relay safety gate` GitHub Actions workflow in
  run `30608587671`.
- Automatic Render deployment remains disabled.

## Published change set

The candidate consists of these coupled groups:

1. Calm-dark public redesign:
   - `app/static/elevate.css`
   - `app/static/elevate.js`
   - `app/static/favicon.svg`
   - `app/static/relay-logo.svg`
   - `app/static/style.css`
   - `app/templates/about.html`
   - `app/templates/base.html`
   - `app/templates/index.html`
2. Operational edge cases and regressions:
   - `app/main.py`
   - `tests/test_trial_containment.py`
3. Local-only exclusion:
   - `.gitignore`
4. Readiness and owner handoff:
   - `README.md`
   - `RELAY_TRIAL_READINESS_AUDIT.html`
   - `docs/DEPENDENCY_REVIEW.md`
   - `docs/OWNER_DECISION_PACKET.md`
   - `docs/OWNER_HANDOFF.md`
   - `docs/RELEASE_SCOPE.md`
   - `docs/TRIAL_EVIDENCE_INDEX.md`
   - `docs/TRIAL_FINAL_REPORT.md`
   - `docs/TRIAL_READINESS_MATRIX.md`

These groups are retained as the historical publication boundary. Subsequent
changes must use a focused pull request and pass the same safety gate.

## What is deliberately excluded

- `Relay Backend Architecture.tldraw` is the owner's local design file. The
  exact root path is ignored and must not be staged or released.
- `.hermes/`, `.playwright-mcp/`, local browser captures, temporary QA
  databases, Python caches, local environments, secrets, database files, dumps,
  and promo source material remain excluded.
- The already tracked hero poster is unchanged and is not requested by the
  redesigned homepage. It is not part of this candidate diff. Publication
  rights must be confirmed before any future re-enable.

For source-boundary verification, the unchanged dormant poster at
`app/static/media/relay-campus-hero-poster.jpg` has SHA-256:

```text
0bfdc8fc3faea383260b5d30d76f586df57cf27527b12249aaf6e5703436cdf1
```

`git ls-files --others --exclude-standard` is empty. Do not use `git add .` or
`git add -A`; stage only the reviewed paths above.

## Verification boundary

The published candidate passes the standard release-scope check, all 88 ordinary
tests, five guarded PostgreSQL 16 migration/concurrency tests, the guarded
Redis/proxy test, production-shaped PostgreSQL/Redis boot and readiness,
dependency and secret checks, and fresh headless responsive/accessibility QA.
The exact-candidate GitHub Actions run passed.

Candidate verification:

```text
python scripts/check_release_scope.py
git diff --check
git ls-files --others --exclude-standard
git diff-tree --no-commit-id --name-only -r HEAD
```

For a clean checkout based on current `origin/main`:

```text
python scripts/check_release_scope.py --require-clean --require-origin-main-base
```

Publication is complete. Deployment and invitations remain separately blocked
by `TRIAL_READINESS_MATRIX.md`.
