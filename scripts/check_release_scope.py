"""Validate Relay's source-only release boundary without exposing file contents."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = {
    Path(".python-version"),
    Path(".github/CODEOWNERS"),
    Path(".github/pull_request_template.md"),
    Path(".github/workflows/ci.yml"),
    Path("RELAY_TRIAL_READINESS_AUDIT.html"),
    Path("docs/OWNER_HANDOFF.md"),
    Path("docs/RELEASE_SCOPE.md"),
    Path("docs/OWNER_DECISION_PACKET.md"),
    Path("docs/STAGING_PROVISIONING_PLAN.md"),
    Path("render.staging.yaml"),
}

FORBIDDEN_PATHS = {
    Path(".playwright-mcp"),
    Path(".Rhistory"),
    Path("docs/page-screenshots-2026-07-14"),
    Path("docs/page-screenshots-dark-2026-07-14"),
    Path("docs/Relay_GitHub_vs_Local_Changes_Report_2026-07-14.pdf"),
    Path("docs/Relay_What_Changed_and_Why_2026-07-14.pdf"),
    Path("del_db.py"),
    Path("fix_double_credits.py"),
    Path("migrate_db.py"),
    Path("fix_dup.py"),
    Path("verify_conservation.py"),
    Path("promo-vids"),
    Path(".hermes"),
    Path("app/static/media/relay-campus-hero-test.mp4"),
    Path("app/static/relay-intro-animation.gif"),
    Path("app/static/relay-intro-animation.mp4"),
    Path("app/static/relay-intro-frames"),
    Path("app/static/relay-pre-smile-mark.png"),
    Path("app/static/relay-pre-smile-mark.svg"),
}

POSTER_PATH = Path("app/static/media/relay-campus-hero-poster.jpg")
POSTER_SHA256 = "0bfdc8fc3faea383260b5d30d76f586df57cf27527b12249aaf6e5703436cdf1"

DATABASE_OR_DUMP_SUFFIXES = {".db", ".dump", ".sqlite", ".sqlite3"}


class ReleaseScopeError(RuntimeError):
    """Raised when the release boundary is not safe to publish."""


def _candidate_files() -> set[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return {
        Path(raw.decode("utf-8"))
        for raw in result.stdout.split(b"\0")
        if raw and (ROOT / raw.decode("utf-8")).is_file()
    }


def _validate_required_paths() -> None:
    missing = sorted(str(path) for path in REQUIRED_PATHS if not (ROOT / path).is_file())
    if missing:
        raise ReleaseScopeError(f"required release paths missing: {', '.join(missing)}")


def _validate_forbidden_paths() -> None:
    candidates = _candidate_files()
    present = sorted(
        str(forbidden)
        for forbidden in FORBIDDEN_PATHS
        if any(path == forbidden or forbidden in path.parents for path in candidates)
    )
    if present:
        raise ReleaseScopeError(f"forbidden release paths present: {', '.join(present)}")


def _validate_local_data_absent() -> None:
    forbidden: list[str] = []
    for path in _candidate_files():
        if path.suffix.lower() in DATABASE_OR_DUMP_SUFFIXES:
            forbidden.append(str(path))
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            forbidden.append(str(path))
        if path.name == ".DS_Store":
            forbidden.append(str(path))
    if forbidden:
        raise ReleaseScopeError(
            "local environment, database, dump, or OS metadata paths present: "
            + ", ".join(sorted(set(forbidden)))
        )


def _validate_poster_identity() -> None:
    poster = ROOT / POSTER_PATH
    if not poster.is_file():
        raise ReleaseScopeError(f"release poster missing: {POSTER_PATH}")
    digest = hashlib.sha256(poster.read_bytes()).hexdigest()
    if digest != POSTER_SHA256:
        raise ReleaseScopeError(
            "release poster changed; update provenance review and the approved release manifest"
        )
    manifest = (ROOT / "docs/RELEASE_SCOPE.md").read_text(encoding="utf-8")
    if POSTER_SHA256 not in manifest:
        raise ReleaseScopeError("release manifest does not identify the current poster digest")


def _validate_clean_worktree() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise ReleaseScopeError("working tree is not clean")


def _validate_origin_main_base() -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReleaseScopeError("HEAD is not based on the fetched origin/main")


def validate(*, require_clean: bool, require_origin_main_base: bool) -> None:
    _validate_required_paths()
    _validate_forbidden_paths()
    _validate_local_data_absent()
    _validate_poster_identity()
    if require_clean:
        _validate_clean_worktree()
    if require_origin_main_base:
        _validate_origin_main_base()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="also require no tracked or untracked worktree changes",
    )
    parser.add_argument(
        "--require-origin-main-base",
        action="store_true",
        help="also require fetched origin/main to be an ancestor of HEAD",
    )
    args = parser.parse_args()
    try:
        validate(
            require_clean=args.require_clean,
            require_origin_main_base=args.require_origin_main_base,
        )
    except (OSError, ReleaseScopeError, subprocess.SubprocessError) as exc:
        print(f"release scope check failed: {exc}", file=sys.stderr)
        return 1
    print("release scope check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
