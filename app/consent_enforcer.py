"""Force re-acceptance of safety-critical consent documents.

Documents listed in SAFETY_CRITICAL_DOCUMENTS trigger an immediate block
when their version changes — the user cannot perform any action until they
re-accept, even if they were mid-session when the version was bumped.
"""

from __future__ import annotations

from .models import ConsentAcceptance

# Documents that require forced re-acceptance on version change.
# These are safety-critical policies that must never be stale.
SAFETY_CRITICAL_DOCUMENTS: frozenset[str] = frozenset({
    "code_of_conduct",
    "safety_rules",
})


def force_reaccept_needed(user_id: str, current_versions: dict[str, str]) -> bool:
    """Check whether the user has stale acceptances for safety-critical documents.

    Returns True if at least one safety-critical document's accepted version
    does not match the current version, meaning the user must re-accept before
    performing any action.
    """
    accepted = {
        row.document: row.version
        for row in ConsentAcceptance.query.filter_by(user_id=user_id).all()
    }
    for doc in SAFETY_CRITICAL_DOCUMENTS:
        current = current_versions.get(doc)
        if current and accepted.get(doc) != current:
            return True
    return False
