"""Threat risk scoring engine (Part 3).

Scores are derived purely from heuristic indicator severities; they are
deterministic and never invented by the LLM.
"""

CRITICAL_WEIGHT = 25
HIGH_WEIGHT = 15
MEDIUM_WEIGHT = 5

SEVERITY_WEIGHTS = {
    "critical": CRITICAL_WEIGHT,
    "high": HIGH_WEIGHT,
    "medium": MEDIUM_WEIGHT,
}


def calculate_score(indicators: list[dict]) -> int:
    """Sum severity weights over indicators, capped at 100."""
    total = 0
    for indicator in indicators:
        severity = str(indicator.get("severity", "medium")).lower()
        total += SEVERITY_WEIGHTS.get(severity, 0)
    return min(total, 100)


def get_severity(score: int) -> str:
    """Map a 0-100 score to the severity_level enum values."""
    if score <= 20:
        return "safe"
    if score <= 40:
        return "low"
    if score <= 60:
        return "medium"
    if score <= 80:
        return "high"
    return "critical"
