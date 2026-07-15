"""Fail on high-confidence committed secret patterns without printing secret values."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PREFIXES = (
    ".git/",
    ".hermes/",
    ".venv/",
    "app/static/media/",
    "app/static/relay-intro-frames/",
    "promo-vids/",
)
EXCLUDED_SUFFIXES = (".gif", ".ico", ".jpeg", ".jpg", ".mov", ".mp4", ".png", ".webp")

# Assemble signature fragments so this checker does not match its own source.
PATTERNS = (
    re.compile(b"AK" + b"IA[0-9A-Z]{16}"),
    re.compile(b"gh" + b"p_[0-9A-Za-z]{36}"),
    re.compile(b"sk_" + b"live_[0-9A-Za-z]{20,}"),
    re.compile(b"-----BEGIN " + b"(?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(b"postgres(?:ql)?://[^\\s/:]+:[^\\s/@]+@"),
)


def candidate_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape")
        if relative.startswith(EXCLUDED_PREFIXES) or relative.lower().endswith(EXCLUDED_SUFFIXES):
            continue
        paths.append(ROOT / relative)
    return paths


def main() -> int:
    flagged = []
    for path in candidate_paths():
        try:
            content = path.read_bytes()
        except (OSError, IsADirectoryError):
            continue
        if b"\0" in content:
            continue
        if any(pattern.search(content) for pattern in PATTERNS):
            flagged.append(path.relative_to(ROOT).as_posix())
    if flagged:
        print("Potential high-confidence secret pattern detected in:", file=sys.stderr)
        for relative in sorted(flagged):
            print(f"- {relative}", file=sys.stderr)
        print("Matched values are intentionally suppressed.", file=sys.stderr)
        return 1
    print("secret pattern check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
