"""NIST/SANS incident response lifecycle state machine (Phase A).

Strict lifecycle over the canonical statuses:

    TRIAGE -> CONTAINMENT -> ERADICATION -> RECOVERY -> CLOSED

with the documented escape hatches: a false positive may be CLOSED directly
from TRIAGE, and an incident may be escalated back to TRIAGE from CONTAINMENT
if containment failed. An analyst therefore cannot accidentally close an
incident that is still being contained — ``validate_transition`` enforces the
matrix below and raises ``InvalidStateTransitionError`` (HTTP 400) otherwise.
"""

from __future__ import annotations

TRIAGE = "TRIAGE"
CONTAINMENT = "CONTAINMENT"
ERADICATION = "ERADICATION"
RECOVERY = "RECOVERY"
CLOSED = "CLOSED"

VALID_STATUSES: frozenset[str] = frozenset(
    {TRIAGE, CONTAINMENT, ERADICATION, RECOVERY, CLOSED}
)

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    TRIAGE: frozenset({CONTAINMENT, CLOSED}),
    CONTAINMENT: frozenset({ERADICATION, TRIAGE}),
    ERADICATION: frozenset({RECOVERY}),
    RECOVERY: frozenset({CLOSED}),
    CLOSED: frozenset(),
}

# Statuses written by the pre-Phase-A API (Postgres enum incident_status).
# They are normalized onto the NIST/SANS lifecycle so legacy rows and legacy
# clients keep working until the enum is migrated.
LEGACY_STATUS_MAP: dict[str, str] = {
    "OPEN": TRIAGE,
    "INVESTIGATING": TRIAGE,
    "CONTAINED": CONTAINMENT,
    "CLOSED": CLOSED,
}


class InvalidStateTransitionError(Exception):
    """A status change violated the lifecycle matrix (maps to HTTP 400)."""

    def __init__(self, message: str, current_status: str, new_status: str) -> None:
        super().__init__(message)
        self.message = message
        self.current_status = current_status
        self.new_status = new_status


def normalize_status(raw_status: str) -> str:
    """Map a stored/requested status onto the canonical lifecycle value.

    Accepts canonical values (case-insensitive) and the legacy enum values
    (open/investigating/contained/closed). Raises ``InvalidStateTransitionError``
    for values that belong to neither set.
    """
    value = raw_status.strip().upper()
    if value in VALID_STATUSES:
        return value
    legacy = LEGACY_STATUS_MAP.get(value)
    if legacy is not None:
        return legacy
    raise InvalidStateTransitionError(
        f"Unknown incident status '{raw_status}'. "
        f"Valid statuses: {', '.join(sorted(VALID_STATUSES))}.",
        current_status=raw_status,
        new_status="",
    )


def allowed_transitions(current_status: str) -> frozenset[str]:
    """Return the statuses that may legally follow ``current_status``."""
    return VALID_TRANSITIONS.get(normalize_status(current_status), frozenset())


def _explain_rejection(current: str, new: str) -> str:
    """Build the analyst-facing message for an illegal transition.

    For moves that skip forward phases the message names the phases that must
    be traversed first (e.g. CONTAINMENT -> CLOSED must go through ERADICATION
    and RECOVERY). Everything else lists what is actually allowed.
    """
    lifecycle_order = [TRIAGE, CONTAINMENT, ERADICATION, RECOVERY, CLOSED]
    if lifecycle_order.index(current) < lifecycle_order.index(new):
        intermediates = lifecycle_order[
            lifecycle_order.index(current) + 1 : lifecycle_order.index(new)
        ]
        return (
            f"Cannot transition from {current} to {new}. "
            f"Must go through {' and '.join(intermediates)} first."
        )
    allowed = sorted(VALID_TRANSITIONS[current])
    allowed_text = ", ".join(allowed) if allowed else "none (terminal state)"
    return (
        f"Cannot transition from {current} to {new}. "
        f"Allowed transitions from {current}: {allowed_text}."
    )


def validate_transition(current_status: str, new_status: str) -> bool:
    """Validate a status change against the lifecycle matrix.

    Returns True when ``current_status -> new_status`` is legal; raises
    ``InvalidStateTransitionError`` otherwise, with a message that names the
    intermediate phases an analyst must go through first.
    """
    current = normalize_status(current_status)
    new = normalize_status(new_status)

    if new in VALID_TRANSITIONS[current]:
        return True

    raise InvalidStateTransitionError(
        _explain_rejection(current, new), current_status=current, new_status=new
    )
