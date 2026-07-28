# Relay owner-ready candidate scope

Last reviewed: 2026-07-23

Status: **OWNER-READY LOCAL CANDIDATE / NO-GO FOR DEPLOYMENT.** This manifest
defines the contents of the owner-approved local candidate commit. It does not
authorize a push, deployment, paid resource, database migration, participant
contact, or launch.

## Base and branch state

- Local `main` and `origin/main` both point to
  `8c775556ae19540089058d4748e001816814855a`.
- The committed base passed the `Relay safety gate` GitHub Actions workflow in
  run `29427792008`.
- The candidate below is saved as one local commit on top of that base. It has
  not been pushed or run in GitHub Actions.
- Automatic Render deployment remains disabled.

## One intended change set

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

These groups were saved together as one local commit. Reconfirm the exact list
with `git diff-tree --no-commit-id --name-only -r HEAD` before authorizing a
push.

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

The local candidate passes the standard release-scope check, all 62 ordinary
tests, five guarded PostgreSQL 16 migration/concurrency tests, the guarded
Redis/proxy test, production-shaped PostgreSQL/Redis boot and readiness,
dependency and secret checks, and fresh headless responsive/accessibility QA.
The exact local candidate still needs its GitHub Actions run after a separately
approved push.

Candidate verification:

```text
python scripts/check_release_scope.py
git diff --check
git ls-files --others --exclude-standard
git diff-tree --no-commit-id --name-only -r HEAD
```

After creating the owner-approved local commit:

```text
python scripts/check_release_scope.py --require-clean --require-origin-main-base
```

The clean-tree form passes for the local candidate. Publication, deployment,
and invitations remain separately blocked by `TRIAL_READINESS_MATRIX.md`.
