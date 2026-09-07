"""Shared interface for media forensics analyzers (Part 5).

Every analyzer returns the same result shape, so a Hugging Face model can
replace or augment a heuristic analyzer later without any API change.

Note: Error Level Analysis and the audio signal statistics are
manipulation-forensics heuristics, not machine-learning deepfake models.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.services.scoring_service import get_severity


class MediaAnalyzer(ABC):
    """Common interface implemented by every media forensics analyzer."""

    method: str = "unknown"
    simulated: bool = False

    @abstractmethod
    def analyze(self, file_bytes: bytes, file_name: str) -> dict[str, Any]:
        """Analyze media bytes and return the unified result dict."""

    def _result(
        self,
        authenticity_score: float,
        manipulation_probability: float,
        indicators: list[dict],
        method: str | None = None,
        simulated: bool | None = None,
    ) -> dict[str, Any]:
        """Build the unified result dict returned by all analyzers."""
        return {
            "authenticity_score": round(float(authenticity_score), 4),
            "manipulation_probability": round(float(manipulation_probability), 4),
            "indicators": indicators,
            "method": method if method is not None else self.method,
            "simulated": self.simulated if simulated is None else simulated,
        }


def severity_from_probability(probability: float) -> str:
    """Map a 0-1 manipulation probability onto the shared severity bands."""
    return get_severity(round(probability * 100))
