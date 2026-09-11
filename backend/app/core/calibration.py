"""Central calibration configuration loader with automatic hot-reload.

All detection thresholds, weights, and scoring rules live in
backend/ml/calibration.json. Changes on disk take effect immediately without
requiring a service restart.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("cyberguard.calibration")

# Resolve backend/ml/calibration.json relative to repository layout
_BACKEND_DIR = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = _BACKEND_DIR / "ml" / "calibration.json"

_cached_calibration: dict[str, Any] = {}
_cached_mtime: float = -1.0

# Built-in fallbacks if file cannot be read
DEFAULT_CALIBRATION: dict[str, Any] = {
    "impersonation": {
        "authority_alone_severity": "low",
        "authority_escalated_severity": "high",
        "benign_cfo_max_severity": "medium",
        "request_indicators": {
            "payment_request": [
                "payment", "invoice", "vendor payment", "wire transfer",
                "remittance", "ach", "direct deposit", "billing", "settle balance"
            ],
            "status_confirmation": [
                "confirm status", "status confirmation", "confirm payment",
                "verify status", "status update", "let me know once done",
                "verify receipt", "has this been processed"
            ],
            "urgency": [
                "urgent", "immediately", "right now", "asap",
                "emergency", "time-sensitive", "do not question"
            ],
            "secrecy": [
                "confidential", "keep this confidential", "strictly confidential",
                "don't tell anyone", "dont tell anyone", "keep this between us",
                "don't inform finance", "dont inform finance", "private matter"
            ],
            "channel_change": [
                "text me", "whatsapp me", "call my personal", "personal email",
                "signal", "telegram", "reach me on", "switch to signal", "message me on"
            ],
        },
    },
    "url_model_version": "v2",
    "deepfake": {
        "splice_score_threshold": 3.0,
        "noise_floor": 0.55,
        "top_percent": 0.05,
        "bot_blocks_cap": 32,
        "block_size": 8,
        "jpeg_quality": 90,
        "uniform_error_mean_max": 0.2,
        "uniform_error_variance_max": 0.005,
        "global_recompression_mean_threshold": 0.2,
        "missing_exif_severity": "low",
        "global_recompression_severity": "low",
        "base_manipulation_probability": 0.05,
        "block_variance_probability_cap": 0.55,
        "container_mismatch_probability": 0.20,
        "uniform_error_probability": 0.10,
        "max_manipulation_probability": 0.95,
        "cnn_real_threshold": 0.10,
        "strong_splice_threshold": 4.0,
        "weak_splice_manipulation_cap": 0.35,
        "manipulation_cap_without_splice": 0.35,
    },
    "scoring": {
        "weights": {
            "critical": 25,
            "high": 16,
            "medium": 5,
            "low": 5,
            "safe": 0,
        },
        "bands": {
            "safe": [0, 20],
            "low": [21, 40],
            "medium": [41, 60],
            "high": [61, 80],
            "critical": [81, 100],
        },
    },
    "explanation": {
        "band_prefix_template": "{band} Risk:",
        "max_retries": 1,
    },
}


def load_calibration() -> dict[str, Any]:
    """Load calibration data from disk, re-reading if mtime changed (hot-reload)."""
    global _cached_calibration, _cached_mtime
    try:
        if not CALIBRATION_PATH.exists():
            if not _cached_calibration:
                _cached_calibration = DEFAULT_CALIBRATION
            return _cached_calibration

        current_mtime = os.path.getmtime(CALIBRATION_PATH)
        if current_mtime != _cached_mtime:
            text = CALIBRATION_PATH.read_text(encoding="utf-8")
            data = json.loads(text)
            _cached_calibration = data
            _cached_mtime = current_mtime
            logger.info("Loaded/reloaded calibration configuration from %s", CALIBRATION_PATH)
    except Exception as exc:
        logger.warning("Failed to load calibration configuration (%s); using cached/defaults", exc)
        if not _cached_calibration:
            _cached_calibration = DEFAULT_CALIBRATION

    return _cached_calibration


def get_calibration() -> dict[str, Any]:
    """Return the active calibration config (checking for hot-reload)."""
    return load_calibration()


def get_deepfake_calibration() -> dict[str, Any]:
    """Return the deepfake forensics calibration section."""
    return get_calibration().get("deepfake", DEFAULT_CALIBRATION["deepfake"])


def get_impersonation_calibration() -> dict[str, Any]:
    """Return the impersonation detector calibration section."""
    return get_calibration().get("impersonation", DEFAULT_CALIBRATION["impersonation"])


def get_scoring_calibration() -> dict[str, Any]:
    """Return the risk scoring calibration section."""
    return get_calibration().get("scoring", DEFAULT_CALIBRATION["scoring"])


def get_explanation_calibration() -> dict[str, Any]:
    """Return the explanation consistency calibration section."""
    return get_calibration().get("explanation", DEFAULT_CALIBRATION["explanation"])
