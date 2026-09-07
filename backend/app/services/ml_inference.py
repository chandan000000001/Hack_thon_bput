"""Hybrid ML inference layer (ML Step 3).

Loads the trained models from ml/models/ (see ml/train_models.py) lazily
and thread-safely, and exposes float-probability predictors. Every getter
returns None (with a logged warning) when a model file is missing or
ml_enabled is false, so the detectors degrade gracefully to
heuristics-only mode — byte-identical to the pre-integration pipeline.

Blending rule applied consistently by the detectors:
    hybrid_score = round(0.45 * heuristic_score + 0.55 * ml_probability * 100)
Each ML contribution is appended to the indicator list as a type "ml_model"
indicator; callers split it back out with split_ml_indicator() so the
heuristic score (calculate_score over non-ML indicators) stays well-defined.
"""

import logging
import math
import threading
from io import BytesIO
from pathlib import Path

import joblib
import numpy as np

from app.core.config import get_settings
from app.services.scoring_service import get_severity

logger = logging.getLogger("cyberguard.ml")

BACKEND_DIR = Path(__file__).resolve().parents[2]

_LOCKS = {
    "email": threading.Lock(),
    "url": threading.Lock(),
    "deepfake": threading.Lock(),
    "network": threading.Lock(),
}
_CACHE: dict[str, object] = {}

# ImageFolder class ordering used at training time (alphabetical):
# index 0 = 'fake', index 1 = 'real'. predict_image returns P(fake).
FAKE_CLASS_INDEX = 0


def models_dir() -> Path:
    """Resolve ML_MODELS_DIR relative to the backend directory."""
    configured = Path(get_settings().ML_MODELS_DIR)
    if configured.is_absolute():
        return configured
    candidate = BACKEND_DIR / configured
    return candidate if candidate.exists() else configured


def _cached(key: str, loader):
    """Thread-safe lazy singleton; caches None after a load failure."""
    if not get_settings().ML_ENABLED:
        return None
    if key in _CACHE:
        return _CACHE[key]
    with _LOCKS[key]:
        if key not in _CACHE:
            try:
                _CACHE[key] = loader()
            except Exception as exc:
                logger.warning("ML model '%s' unavailable — heuristics-only mode: %s", key, exc)
                _CACHE[key] = None
    return _CACHE[key]


# ---------------------------------------------------------------------------
# Model loaders
# ---------------------------------------------------------------------------

def _load_email_model():
    base = models_dir()
    vectorizer = joblib.load(base / "email_tfidf.pkl")
    model = joblib.load(base / "email_phishing_xgb.pkl")
    return vectorizer, model


def _load_url_model():
    return joblib.load(models_dir() / "url_xgb.pkl")


def _load_deepfake_model():
    import torch
    import torch.nn as nn

    model = nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Linear(32 * 8 * 8, 64), nn.ReLU(),
        nn.Linear(64, 2),
    )
    state_dict = torch.load(models_dir() / "deepfake_cnn.pt", map_location="cpu")
    model.load_state_dict(state_dict)
    model.eval()
    return model


def _load_network_model():
    """Load scaler + XGBoost model, and re-derive the service LabelEncoder
    from the raw training CSV (the preprocessing-time encoder was not
    persisted; LabelEncoder is deterministic, so refitting on the same
    column reproduces the exact training-time encoding)."""
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder

    base = models_dir()
    scaler = joblib.load(base / "network_scaler.pkl")
    model = joblib.load(base / "network_xgb.pkl")

    raw_path = base.parent / "data" / "raw_network.csv"
    service_encoder = LabelEncoder()
    if raw_path.exists():
        frame = pd.read_csv(raw_path, usecols=["f1"])
        service_encoder.fit(frame["f1"].astype(str))
    else:  # pragma: no cover - preprocessing output must exist for ML mode
        logger.warning("raw_network.csv not found; service encoding may be incomplete")
    return scaler, model, service_encoder


def get_email_model():
    return _cached("email", _load_email_model)


def get_url_model():
    return _cached("url", _load_url_model)


def get_deepfake_model():
    return _cached("deepfake", _load_deepfake_model)


def get_network_model():
    return _cached("network", _load_network_model)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def shannon_entropy(value: str) -> float:
    # MUST remain identical to training (ml/train_models.py).
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


SUSPICIOUS_URL_TLDS = {"xyz", "top", "zip", "ru", "cn", "tk", "click", "link", "work", "loan", "cam", "rest"}


def extract_url_features(url: str) -> np.ndarray:
    """MUST remain identical to training (ml/train_models.py): identical
    feature order [length, entropy, digit_ratio, has_ip, has_at_symbol,
    suspicious_tld, http_only, num_subdomains] and identical logic."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except ValueError:
        parsed = urlparse(f"http://{url}")
    host = parsed.hostname or ""
    scheme = parsed.scheme

    digits = sum(char.isdigit() for char in url)
    alnum = sum(char.isalnum() for char in url)
    digit_ratio = digits / alnum if alnum else 0.0

    is_ip = bool(host) and host.replace(".", "").isdigit() and host.count(".") == 3
    tld = host.rsplit(".", 1)[-1].lower() if "." in host else ""
    subdomains = max(0, len([part for part in host.split(".") if part]) - 2)

    return np.array(
        [
            len(url),
            shannon_entropy(url),
            digit_ratio,
            1.0 if is_ip else 0.0,
            1.0 if "@" in url else 0.0,
            1.0 if tld in SUSPICIOUS_URL_TLDS else 0.0,
            1.0 if scheme == "http" else 0.0,
            float(subdomains),
        ],
        dtype=np.float64,
    )


def _image_tensor(image_bytes: bytes):
    """PIL-decode bytes -> resize 32x32 -> ToTensor -> Normalize(0.5)."""
    import torch
    from PIL import Image
    from torchvision import transforms

    transform = transforms.Compose(
        [
            transforms.Resize((32, 32)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ]
    )
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    return transform(image).unsqueeze(0)


# ---------------------------------------------------------------------------
# Public predictors — float probabilities, None when unavailable
# ---------------------------------------------------------------------------

def predict_email(text: str) -> float | None:
    """Probability (0-1) that the text is phishing."""
    bundle = get_email_model()
    if bundle is None:
        return None
    try:
        vectorizer, model = bundle
        proba = model.predict_proba(vectorizer.transform([text]))
        return float(proba[0][1])
    except Exception as exc:
        logger.warning("email ML inference failed: %s", exc)
        return None


def predict_url(url: str) -> float | None:
    """Probability (0-1) that the URL is malicious."""
    model = get_url_model()
    if model is None:
        return None
    try:
        features = extract_url_features(url).reshape(1, -1)
        return float(model.predict_proba(features)[0][1])
    except Exception as exc:
        logger.warning("url ML inference failed: %s", exc)
        return None


def predict_image(image_bytes: bytes) -> float | None:
    """Probability (0-1) that the image is AI-generated/manipulated (class 'fake')."""
    model = get_deepfake_model()
    if model is None:
        return None
    try:
        import torch

        with torch.no_grad():
            tensor = _image_tensor(image_bytes)
            logits = model(tensor)
            probability = torch.softmax(logits, dim=1)[0][FAKE_CLASS_INDEX]
            return float(probability)
    except Exception as exc:
        logger.warning("image ML inference failed: %s", exc)
        return None


def predict_network(feature_row: list) -> float | None:
    """Probability (0-1) that a feature row is an attack (label != 'normal').

    feature_row must follow the ml/data/train_network.csv column order
    (f0..f3); f1 may be the raw service name, which is encoded here with
    the training-time LabelEncoder. Returns None for unseen services.
    """
    bundle = get_network_model()
    if bundle is None:
        return None
    try:
        import pandas as pd

        scaler, model, service_encoder = bundle
        row = list(feature_row)
        if isinstance(row[1], str):
            row[1] = int(service_encoder.transform([row[1]])[0])
        # DataFrame with the training-time column names avoids sklearn's
        # "X does not have valid feature names" warning.
        columns = getattr(scaler, "feature_names_in_", None)
        frame = pd.DataFrame([row], columns=columns) if columns is not None else [row]
        scaled = scaler.transform(frame)
        return float(model.predict_proba(scaled)[0][1])
    except Exception as exc:
        logger.warning("network ML inference failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Hybrid blending helpers
# ---------------------------------------------------------------------------

def blend_scores(heuristic_score: int, ml_probability: float) -> int:
    """Monotonic hybrid blending — SAFETY PRINCIPLE: a trained model may
    raise a score but may NEVER lower it below the heuristic verdict.

        final_score = max(heuristic_score, round(0.45 * heuristic_score + 0.55 * ml_probability * 100))

    This prevents a weak or mismatched ML signal from diluting a strong
    heuristic verdict (e.g. a C2-port exfiltration event must never be
    downgraded to Safe because the model saw no similar attack)."""
    blended = round(0.45 * heuristic_score + 0.55 * ml_probability * 100)
    blended = max(0, min(100, blended))
    return max(heuristic_score, blended)


def ml_indicator(artifact: str, probability: float) -> dict:
    """Indicator documenting an ML contribution (severity from the band).
    Carries the numeric probability so callers can blend without re-parsing."""
    return {
        "type": "ml_model",
        "value": artifact,
        "severity": get_severity(round(probability * 100)),
        "description": f"Trained model probability: {probability:.2f}",
        "probability": round(probability, 4),
    }


def split_ml_indicator(indicators: list[dict]) -> tuple[list[dict], float | None]:
    """Separate ml_model indicators (which must not add heuristic weight)
    from heuristic indicators, returning (heuristic_indicators, ml_probability).
    The last ml_model indicator with a probability wins if several are present."""
    probability = None
    heuristic = []
    for indicator in indicators:
        if indicator.get("type") == "ml_model":
            if isinstance(indicator.get("probability"), (int, float)):
                probability = float(indicator["probability"])
            continue
        heuristic.append(indicator)
    return heuristic, probability


def score_with_ml(indicators: list[dict]) -> tuple[int, int, float | None]:
    """Return (heuristic_score, hybrid_score, ml_probability) for a detector's
    indicator list. hybrid == heuristic when no ML probability is present."""
    from app.services.scoring_service import calculate_score

    heuristic_indicators, probability = split_ml_indicator(indicators)
    heuristic_score = calculate_score(heuristic_indicators)
    hybrid_score = blend_scores(heuristic_score, probability) if probability is not None else heuristic_score
    return heuristic_score, hybrid_score, probability
