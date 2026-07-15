# Relay controlled-trial release scope

Last reviewed: 2026-07-14

Status: **LOCAL RELEASE CANDIDATE / NO-GO FOR DEPLOYMENT.** This manifest defines
the intended Git scope. It does not authorize a commit, push, deployment,
credential change, participant contact, or trial launch.

## Remote reconciliation

The reviewed remote head is `9fbc1ea19fcb8b9353bf8d61619d62a2b46767ec`.
Its useful intent—removing the out-of-home campaign from the trial homepage—is
already met by the controlled-trial template, which does not render the
campaign, maps, street mockups, or paid plans.

The remote commit also adds three unsafe one-off utilities:

- `del_db.py` deletes a developer-specific SQLite file and may kill Python
  processes.
- `fix_double_credits.py` edits account balances directly instead of appending
  an attributable ledger event.
- `migrate_db.py` performs developer-specific SQLite schema changes outside
  Alembic.

The local release branch must be based on the reviewed remote head, retain the
controlled-trial homepage, and delete all three utilities. Versioned migrations,
read-only reconciliation, and attributable ledger operations supersede them.

### Read-only reconciliation proof

On 2026-07-14, a three-way merge simulation used the local controlled-trial
homepage as the current file, local `HEAD` as the common base, and
`origin/main` as the incoming version. It returned status `0`, produced no
conflict markers, and its merged output matched the current local
`app/templates/index.html` byte-for-byte. The three incoming utility paths are
absent locally. This proves the content decision is conflict-free; it does not
alter branch ancestry or authorize the still-required local commit.

## Intended release groups

The candidate is one coupled change set. Do not commit only part of a group.

1. Application and policy:
   - `.env.example`, `app/database.py`, `app/main.py`, `app/models.py`
   - `app/email_service.py`, `app/ledger.py`, `app/policies.py`,
     `app/session_service.py`, `app/trial_config.py`
2. Product surface:
   - all modified templates and CSS/JavaScript under `app/templates/` and
     `app/static/`
   - new `conduct.html`, `consent.html`, `moderator_queue.html`, and
     `session_details.html`
3. Release-critical media:
   - `app/static/media/relay-campus-hero-poster.jpg`
4. Database and verification:
   - `migrations/`, `tests/`, `scripts/`, `requirements.txt`, and
     `requirements-dev.txt`
5. Delivery and evidence:
   - `.python-version`, `.github/CODEOWNERS`,
     `.github/pull_request_template.md`, `.github/workflows/ci.yml`,
     `.gitignore`, `render.yaml`, `render.staging.yaml`, and `README.md`
   - `RELAY_BUSINESS_PLAN.md`, `RELAY_DOC.md`,
     `RELAY_TRIAL_READINESS_AUDIT.html`, and `docs/`
6. Intentional removals:
   - local obsolete `fix_dup.py` and `verify_conservation.py`
   - remote-only `del_db.py`, `fix_double_credits.py`, and `migrate_db.py`

Recount the exact path totals after every scope change and after rebasing onto
the reviewed remote head. The staging blueprint is a reviewed proposal only;
syncing it would create paid resources and requires separate owner approval.

## Deliberately excluded local material

Narrow `.gitignore` rules keep these files local without deleting them:

- `.DS_Store` and `.hermes/`
- `.playwright-mcp/` and `.Rhistory`
- generated `docs/page-screenshots-*/` captures and point-in-time PDF reports;
  the reviewed Markdown sources remain canonical
- all of `promo-vids/`
- `app/static/media/relay-campus-hero-test.mp4`
- `app/static/relay-intro-animation.gif` and `.mp4`
- `app/static/relay-intro-frames/`
- `app/static/relay-pre-smile-mark.png` and `.svg`
- ignored environments, databases, secrets, and Python caches

Do not use `git add .` or `git add -A`. Stage only the intended release groups
and confirm the cached name list before committing.

## Media provenance boundary

The rendered hero poster is 1,920×1,080 JPEG content with SHA-256:

```text
0bfdc8fc3faea383260b5d30d76f586df57cf27527b12249aaf6e5703436cdf1
```

It has no embedded author, copyright, license, or source metadata. It contains
a branded campus composite and incidental student figures. The owner must
attest that Relay may publish it, or it must be replaced with an approved asset
and the browser/asset-budget evidence rerun. Until then, release scope is not
fully approved.

## Commit boundary

The final local branch must:

- be based on the reviewed `origin/main` object;
- contain no unsafe utility, ignored local artifact, secret, database, dump, or
  participant identifier;
- pass the complete local verification set and network-backed advisory scans;
- have a clean working tree after the intentional local commit; and
- remain unpushed until the owner chooses to publish it.

Run `python scripts/check_release_scope.py` before staging. After the approved
local commit and remote-base reconciliation, also run:

```text
python scripts/check_release_scope.py --require-clean --require-origin-main-base
```

The check proves the source boundary and poster identity only. It does not
prove publication rights, approve the media, or authorize a release.

Deployment and invitations remain separately blocked by the launch gates in
`TRIAL_READINESS_MATRIX.md`.
