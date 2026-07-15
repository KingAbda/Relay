"""Check exact direct requirement pins against PyPI's OSV-backed release metadata."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.requirements import InvalidRequirement, Requirement


ROOT = Path(__file__).resolve().parents[1]
def direct_pins() -> list[tuple[str, str]]:
    pins = []
    for line_number, raw in enumerate(
        (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            raise RuntimeError(
                f"requirements.txt:{line_number} is not a valid requirement"
            ) from exc
        specifiers = list(requirement.specifier)
        if (
            requirement.url is not None
            or requirement.marker is not None
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            raise RuntimeError(
                f"requirements.txt:{line_number} is not an exact package==version pin"
            )
        pins.append((requirement.name, specifiers[0].version))
    return pins


def release_vulnerabilities(name: str, version: str) -> list[dict]:
    url = f"https://pypi.org/pypi/{quote(name)}/{quote(version)}/json"
    request = Request(url, headers={"User-Agent": "Relay-direct-advisory-check/1"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Unable to obtain advisory metadata for {name}=={version}; failing closed"
        ) from exc
    return payload.get("vulnerabilities") or []


def main() -> int:
    affected = []
    try:
        pins = direct_pins()
        for name, version in pins:
            vulnerabilities = release_vulnerabilities(name, version)
            if vulnerabilities:
                affected.append(
                    {
                        "package": name,
                        "version": version,
                        "advisories": sorted(
                            {row.get("id", "unknown") for row in vulnerabilities}
                        ),
                        "fixed_in": sorted(
                            {
                                fixed
                                for row in vulnerabilities
                                for fixed in (row.get("fixed_in") or [])
                            }
                        ),
                    }
                )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if affected:
        print("Direct dependency advisory check failed:", file=sys.stderr)
        for result in affected:
            fixes = ", ".join(result["fixed_in"]) or "not listed"
            advisory_ids = ", ".join(result["advisories"])
            print(
                f"- {result['package']}=={result['version']}: {advisory_ids}; fixed in {fixes}",
                file=sys.stderr,
            )
        return 1
    print(f"direct advisory check passed for {len(pins)} exact pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
