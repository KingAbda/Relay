"""Fail closed when Relay's readiness evidence artifacts drift apart."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "TRIAL_READINESS_MATRIX.md"
EVIDENCE_INDEX = ROOT / "docs" / "TRIAL_EVIDENCE_INDEX.md"
FINAL_REPORT = ROOT / "docs" / "TRIAL_FINAL_REPORT.md"
HTML_AUDIT = ROOT / "RELAY_TRIAL_READINESS_AUDIT.html"

ALLOWED_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT TESTED"}
EXPECTED_ISSUE_IDS = (
    tuple(f"C{number:02d}" for number in range(1, 16))
    + tuple(f"H{number:02d}" for number in range(1, 18))
    + tuple(f"M{number:02d}" for number in range(1, 17))
    + tuple(f"L{number:02d}" for number in range(1, 3))
)
EXPECTED_GATE_IDS = tuple(f"G{number:02d}" for number in range(1, 13))


class ReadinessArtifactError(RuntimeError):
    """Raised when an evidence artifact is missing or internally inconsistent."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReadinessArtifactError(f"Cannot read {path.relative_to(ROOT)}: {exc}") from exc


def _split_markdown_table_row(line: str) -> list[str]:
    """Split a simple Markdown table row without treating pipes in code spans as columns."""
    columns = []
    current = []
    in_code = False
    escaped = False
    for character in line.strip().strip("|"):
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\":
            current.append(character)
            escaped = True
            continue
        if character == "`":
            in_code = not in_code
            current.append(character)
            continue
        if character == "|" and not in_code:
            columns.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    if in_code:
        raise ReadinessArtifactError("Markdown table row contains an unclosed code span")
    columns.append("".join(current).strip())
    return columns


def _markdown_rows(path: Path, id_pattern: str, expected_columns: int) -> list[list[str]]:
    rows = []
    matcher = re.compile(rf"^\| ({id_pattern}) \|")
    for line_number, line in enumerate(_read(path).splitlines(), start=1):
        if not matcher.match(line):
            continue
        try:
            columns = _split_markdown_table_row(line)
        except ReadinessArtifactError as exc:
            raise ReadinessArtifactError(
                f"{path.relative_to(ROOT)}:{line_number}: {exc}"
            ) from exc
        if len(columns) != expected_columns:
            raise ReadinessArtifactError(
                f"{path.relative_to(ROOT)}:{line_number} has {len(columns)} columns; "
                f"expected {expected_columns}"
            )
        rows.append(columns)
    return rows


def _assert_ids(label: str, actual: list[str], expected: tuple[str, ...]) -> None:
    if len(actual) != len(set(actual)):
        duplicates = sorted(identifier for identifier, count in Counter(actual).items() if count > 1)
        raise ReadinessArtifactError(f"{label} contains duplicate IDs: {', '.join(duplicates)}")
    if tuple(actual) != expected:
        missing = [identifier for identifier in expected if identifier not in actual]
        extra = [identifier for identifier in actual if identifier not in expected]
        raise ReadinessArtifactError(
            f"{label} ID/order mismatch; missing={missing or 'none'}, extra={extra or 'none'}"
        )


def _status_summary(counts: Counter[str], total: int) -> str:
    return (
        f"{counts['PASS']} PASS, {counts['FAIL']} FAIL, "
        f"{counts['BLOCKED']} BLOCKED, {counts['NOT TESTED']} NOT TESTED ({total} total)"
    )


def validate() -> dict[str, object]:
    issue_rows = _markdown_rows(MATRIX, r"[CHML]\d{2}", 7)
    gate_rows = _markdown_rows(MATRIX, r"G\d{2}", 6)
    index_issue_rows = _markdown_rows(EVIDENCE_INDEX, r"[CHML]\d{2}", 3)
    index_gate_rows = _markdown_rows(EVIDENCE_INDEX, r"G\d{2}", 3)

    issue_ids = [row[0] for row in issue_rows]
    gate_ids = [row[0] for row in gate_rows]
    _assert_ids("readiness matrix issues", issue_ids, EXPECTED_ISSUE_IDS)
    _assert_ids("readiness matrix gates", gate_ids, EXPECTED_GATE_IDS)
    _assert_ids(
        "evidence index issues",
        [row[0] for row in index_issue_rows],
        EXPECTED_ISSUE_IDS,
    )
    _assert_ids(
        "evidence index gates",
        [row[0] for row in index_gate_rows],
        EXPECTED_GATE_IDS,
    )

    issue_statuses = {row[0]: row[3] for row in issue_rows}
    gate_statuses = {row[0]: row[2] for row in gate_rows}
    unknown_statuses = (
        set(issue_statuses.values()) | set(gate_statuses.values())
    ) - ALLOWED_STATUSES
    if unknown_statuses:
        raise ReadinessArtifactError(
            f"Matrix contains unknown statuses: {', '.join(sorted(unknown_statuses))}"
        )

    for row in issue_rows:
        identifier, severity, finding, status, evidence, blocker, owner = row
        expected_severity = {
            "C": "Critical",
            "H": "High",
            "M": "Medium",
            "L": "Low",
        }[identifier[0]]
        if severity != expected_severity:
            raise ReadinessArtifactError(
                f"{identifier} severity is {severity!r}; expected {expected_severity!r}"
            )
        if not all((finding, status, evidence, blocker, owner)):
            raise ReadinessArtifactError(f"{identifier} has an empty matrix evidence field")
    for row in gate_rows:
        if not all(row):
            raise ReadinessArtifactError(f"{row[0]} has an empty matrix evidence field")
    for row in index_issue_rows + index_gate_rows:
        if not all(row):
            raise ReadinessArtifactError(f"{row[0]} has an empty evidence-index field")

    html = _read(HTML_AUDIT)
    issue_data_match = re.search(
        r"const issueEvidence = (\[[\s\S]*?\n\s*\]);\n\n\s*if",
        html,
    )
    if not issue_data_match:
        raise ReadinessArtifactError("HTML audit has no parseable issueEvidence array")
    try:
        html_issue_rows = json.loads(issue_data_match.group(1))
    except json.JSONDecodeError as exc:
        raise ReadinessArtifactError(f"HTML issueEvidence is invalid JSON: {exc}") from exc
    if any(not isinstance(row, list) or len(row) != 4 for row in html_issue_rows):
        raise ReadinessArtifactError("Every HTML issueEvidence row must have four fields")
    html_issue_ids = [row[0] for row in html_issue_rows]
    _assert_ids("HTML audit issues", html_issue_ids, EXPECTED_ISSUE_IDS)
    html_issue_statuses = {row[0]: row[1] for row in html_issue_rows}
    if html_issue_statuses != issue_statuses:
        raise ReadinessArtifactError("HTML issue statuses do not match the readiness matrix")
    if any(not row[2].strip() or not row[3].strip() for row in html_issue_rows):
        raise ReadinessArtifactError("HTML issue evidence and blocker text must be non-empty")
    html_issue_elements = re.findall(r'<details class="issue"(?:\s|>)', html)
    if len(html_issue_elements) != len(EXPECTED_ISSUE_IDS):
        raise ReadinessArtifactError(
            f"HTML has {len(html_issue_elements)} issue elements; expected {len(EXPECTED_ISSUE_IDS)}"
        )

    html_gate_rows = re.findall(
        r'<article class="gate-card" data-gate="(G\d{2})">[\s\S]*?'
        r'<span class="status-pill status-[^"]+">(PASS|FAIL|BLOCKED|NOT TESTED)</span>'
        r"[\s\S]*?</article>",
        html,
    )
    html_gate_ids = [row[0] for row in html_gate_rows]
    _assert_ids("HTML audit gates", html_gate_ids, EXPECTED_GATE_IDS)
    if dict(html_gate_rows) != gate_statuses:
        raise ReadinessArtifactError("HTML gate statuses do not match the readiness matrix")

    final_report = _read(FINAL_REPORT)
    issue_counts = Counter(issue_statuses.values())
    gate_counts = Counter(gate_statuses.values())
    issue_summary = _status_summary(issue_counts, len(EXPECTED_ISSUE_IDS))
    gate_summary = _status_summary(gate_counts, len(EXPECTED_GATE_IDS))
    if f"Audit issues: {issue_summary}." not in final_report:
        raise ReadinessArtifactError("Final report issue-status summary does not match the matrix")
    if f"Launch gates: {gate_summary}." not in final_report:
        raise ReadinessArtifactError("Final report gate-status summary does not match the matrix")
    if "**NO-GO.**" not in final_report or "Verdict: **NO-GO**" not in _read(MATRIX):
        raise ReadinessArtifactError("Matrix and final report must retain an explicit NO-GO verdict")

    return {
        "issues": len(issue_ids),
        "issue_statuses": dict(sorted(issue_counts.items())),
        "gates": len(gate_ids),
        "gate_statuses": dict(sorted(gate_counts.items())),
    }


def main() -> int:
    try:
        result = validate()
    except ReadinessArtifactError as exc:
        print(f"readiness artifact check failed: {exc}", file=sys.stderr)
        return 1
    print(f"readiness artifact check passed: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
