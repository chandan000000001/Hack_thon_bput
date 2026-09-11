"""Threat risk scoring engine (Part 3).

Scores are derived purely from heuristic indicator severities; they are
deterministic and never invented by the LLM.
"""

from app.core.calibration import get_scoring_calibration

CRITICAL_WEIGHT = 25
HIGH_WEIGHT = 15
MEDIUM_WEIGHT = 5
LOW_WEIGHT = 5

SEVERITY_WEIGHTS = {
    "critical": CRITICAL_WEIGHT,
    "high": HIGH_WEIGHT,
    "medium": MEDIUM_WEIGHT,
    "low": LOW_WEIGHT,
}


def calculate_score(indicators: list[dict]) -> int:
    """Sum severity weights over indicators, capped at 100."""
    calib_weights = get_scoring_calibration().get("weights", SEVERITY_WEIGHTS)
    total = 0
    for indicator in indicators:
        severity = str(indicator.get("severity", "medium")).lower()
        weight = calib_weights.get(severity, SEVERITY_WEIGHTS.get(severity, 0))
        total += weight
    return min(total, 100)


def get_severity(score: int) -> str:
    """Map a 0-100 score to the severity_level enum values."""
    calib = get_scoring_calibration()
    bands = calib.get("bands")
    if bands:
        for band_name, (low, high) in bands.items():
            if low <= score <= high:
                return band_name

    if score <= 20:
        return "safe"
    if score <= 40:
        return "low"
    if score <= 60:
        return "medium"
    if score <= 80:
        return "high"
    return "critical"

