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
import re
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
    "audio": threading.Lock(),
}
_CACHE: dict[str, object] = {}


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
    """Load the email phishing model selected by ml/models/calibration.json.

    Version "v2" is the multilingual char-n-gram (2-4) TF-IDF + XGBoost pair
    (email_tfidf_v2.pkl / email_phishing_xgb_v2.pkl) trained on en + hi + te +
    or + romanised rows — it scores every language without translation.
    Version "v1" is the original word-TF-IDF pair. If the calibrated version's
    artifacts are missing, the loader falls back to v1 (logged) so inference
    never breaks after an incomplete deploy.
    """
    base = models_dir()
    try:
        if email_model_version() == "v2":
            vectorizer = joblib.load(base / "email_tfidf_v2.pkl")
            model = joblib.load(base / "email_phishing_xgb_v2.pkl")
            return vectorizer, model, "email_phishing_xgb_v2.pkl"
    except Exception as exc:
        logger.warning("email model v2 unavailable — falling back to v1: %s", exc)
    vectorizer = joblib.load(base / "email_tfidf.pkl")
    model = joblib.load(base / "email_phishing_xgb.pkl")
    return vectorizer, model, "email_phishing_xgb.pkl"


def email_model_version() -> str:
    """Read the active email model version from models_dir()/calibration.json.

    Missing file or unknown value -> "v1" (the pre-Indic default).
    """
    try:
        import json

        with (models_dir() / "calibration.json").open(encoding="utf-8") as fh:
            calibration = json.load(fh)
        version = str(calibration.get("email_model_version", "v1"))
        return version if version in ("v1", "v2") else "v1"
    except Exception:
        return "v1"


def email_model_artifact() -> str:
    """Return the XGBoost artifact filename backing the active version.

    Resolved from the cached bundle once loaded; falls back to the
    version-derived name so the ml_model indicator is accurate even before
    the first inference.
    """
    bundle = get_email_model()
    if bundle is not None:
        return bundle[2]
    return "email_phishing_xgb_v2.pkl" if email_model_version() == "v2" else "email_phishing_xgb.pkl"


def url_model_version() -> str:
    """Read active URL model version from models_dir()/calibration.json or calibration config."""
    try:
        import json

        with (models_dir() / "calibration.json").open(encoding="utf-8") as fh:
            calibration = json.load(fh)
        version = str(calibration.get("url_model_version", "v2"))
        return version if version in ("v1", "v2") else "v2"
    except Exception:
        try:
            from app.core.calibration import get_calibration

            version = str(get_calibration().get("url_model_version", "v2"))
            return version if version in ("v1", "v2") else "v2"
        except Exception:
            return "v2"


def url_model_artifact() -> str:
    """Return the active URL XGBoost model artifact filename."""
    bundle = get_url_model()
    if bundle is not None:
        return bundle[1]
    return "url_xgb_v2.pkl" if url_model_version() == "v2" else "url_xgb.pkl"


def _load_url_model():
    base = models_dir()
    if url_model_version() == "v2":
        try:
            model = joblib.load(base / "url_xgb_v2.pkl")
            return model, "url_xgb_v2.pkl"
        except Exception as exc:
            logger.warning("url model v2 unavailable — falling back to v1: %s", exc)
    model = joblib.load(base / "url_xgb.pkl")
    return model, "url_xgb.pkl"


_DEEPFAKE_LOADED_ARTIFACT: str | None = None


def _load_deepfake_model():
    """Load the 128px deepfake artifact selected by ml/models/calibration.json.

    ``deepfake_model_version`` selects the artifact filename
    (``deepfake_cnn_<version>.pt`` — currently v2: MobileNetV3-Small trained on
    GenImage real + messenger-degraded reals vs StableDiffusion/Midjourney
    fakes, ml/train_deepfake_v2.py). There is exactly ONE neural artifact: the
    old 32x32 v1 CNN was deleted, so a missing selected file is NOT a neural
    fallback — get_deepfake_model() returns None and the detector degrades to
    heuristics-only (ELA splice + metadata) with an explicit
    "heuristics-only-fallback" ml_model indicator and a logged warning.
    """
    import torch
    import torch.nn as nn
    from torchvision import models as tv_models

    global _DEEPFAKE_LOADED_ARTIFACT
    version = deepfake_model_version()
    artifact = deepfake_artifact_for_version(version)
    base = models_dir()
    if not (base / artifact).exists():
        logger.warning(
            "deepfake model %s selected by calibration but %s is missing — "
            "heuristics-only fallback (no neural inference)",
            version,
            artifact,
        )
        _DEEPFAKE_LOADED_ARTIFACT = None
        return None
    try:
        model = tv_models.mobilenet_v3_small(weights=None)
        model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, 2)
        state_dict = torch.load(base / artifact, map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()
        _DEEPFAKE_LOADED_ARTIFACT = artifact
        return model
    except Exception as exc:
        logger.warning(
            "deepfake model %s failed to load (%s) — heuristics-only fallback",
            artifact,
            exc,
        )
        _DEEPFAKE_LOADED_ARTIFACT = None
        return None


def deepfake_artifact_for_version(version: str) -> str:
    """Map a calibration version (v2, v3, ...) to its artifact filename."""
    return f"deepfake_cnn_{version}.pt"


def deepfake_model_version() -> str:
    """Read the active deepfake model version from models_dir()/calibration.json.

    Missing file or unknown value -> "v2" (the current neural artifact).
    """
    try:
        import json

        with (models_dir() / "calibration.json").open(encoding="utf-8") as fh:
            calibration = json.load(fh)
        version = str(calibration.get("deepfake_model_version", "v2"))
        return version if re.fullmatch(r"v\d+", version) else "v2"
    except Exception:
        return "v2"


def deepfake_model_artifact() -> str:
    """Return the artifact filename for the selected deepfake version.

    After the first inference this reflects what the loader actually loaded —
    which is always the selected artifact or nothing (heuristics-only).
    Callers use this to label ml_model indicators and to detect the degraded
    mode (deepfake_degraded()).
    """
    get_deepfake_model()
    return _DEEPFAKE_LOADED_ARTIFACT or deepfake_artifact_for_version(
        deepfake_model_version()
    )


def deepfake_degraded() -> bool:
    """True when the selected deepfake artifact is unavailable.

    In this mode deepfake detection runs on the ELA/metadata heuristics alone
    and every media response carries an ml_model indicator with value
    "heuristics-only-fallback" (no neural inference, no silent old-model
    fallback).
    """
    get_deepfake_model()
    return _DEEPFAKE_LOADED_ARTIFACT is None


def deepfake_deployment_status(light: bool = True) -> dict[str, object]:
    """Deployment info for the startup log and /health/deep.

    light=True (startup log) only checks artifact existence on disk — no
    weight loading; light=False (authenticated diagnostics) resolves the
    actually-loaded state, including a load failure at request time.
    """
    version = deepfake_model_version()
    artifact = deepfake_artifact_for_version(version)
    if light:
        degraded = not (models_dir() / artifact).exists()
    else:
        get_deepfake_model()
        degraded = _DEEPFAKE_LOADED_ARTIFACT is None
    return {
        "deepfake": {
            "version": version,
            "artifact": artifact,
            "heuristics_only": degraded,
        },
        "audio": audio_deployment_status(),
    }


# ---------------------------------------------------------------------------
# Audio anti-spoofing model (audio_cnn_v1) — trained by ml/train_audio_v1.py
# ---------------------------------------------------------------------------

AUDIO_ARTIFACT = "audio_cnn_v1.pt"


def audio_model_version() -> str:
    """Read the active audio model version from models_dir()/calibration.json.

    Values: "v1" serves the trained LCNN artifact (audio_cnn_v1.pt);
    "simulated" keeps the pre-model simulated hash-based audio scoring.
    Missing file or unknown value -> "simulated" (the safe default).
    """
    try:
        import json

        with (models_dir() / "calibration.json").open(encoding="utf-8") as fh:
            calibration = json.load(fh)
        version = str(calibration.get("audio_model_version", "simulated"))
        return version if version in ("v1", "simulated") else "simulated"
    except Exception:
        return "simulated"


def _load_audio_model():
    """Load the audio LCNN artifact when calibration selects v1 and it exists."""
    from ml.audio_model import load_audio_artifact

    if audio_model_version() != "v1":
        return None
    base = models_dir()
    if not (base / AUDIO_ARTIFACT).exists():
        logger.warning(
            "audio model v1 selected by calibration but %s is missing — "
            "audio analysis falls back to the simulated hash path",
            AUDIO_ARTIFACT,
        )
        return None
    try:
        model, mean, std = load_audio_artifact(base / AUDIO_ARTIFACT)
        return model, mean, std
    except Exception as exc:
        logger.warning("audio model %s failed to load (%s) — simulated fallback", AUDIO_ARTIFACT, exc)
        return None


def get_audio_model():
    """Thread-safe lazy loader. Returns (model, handcraft_mean, handcraft_std) or None."""
    return _cached("audio", _load_audio_model)


def audio_model_available() -> bool:
    """True when the trained audio model is loaded and will serve inference."""
    return get_audio_model() is not None


def audio_deployment_status() -> dict[str, object]:
    """Deployment info for the startup log and /health/deep."""
    version = audio_model_version()
    available = audio_model_available()
    return {
        "version": version,
        "artifact": AUDIO_ARTIFACT if version == "v1" else None,
        "model_loaded": available,
        "mode": "trained_model" if available else "simulated_fallback",
    }


def predict_audio(file_bytes: bytes, file_name: str = "") -> dict | None:
    """Audio anti-spoofing inference over 3s crops.

    Decodes any container to 16 kHz mono, splits into 3-second crops (50%
    overlap), scores every crop with the LCNN model and returns
    {"mean_prob", "max_prob", "n_crops"} — callers flag on the max crop
    probability and keep the mean as context. Returns None when the model is
    unavailable or decoding/inference fails, so callers keep the pre-model
    behaviour.
    """
    bundle = get_audio_model()
    if bundle is None:
        return None
    try:
        import torch

        from ml.audio_features import (
            decode_audio_16k,
            extract_crop_features,
            make_crops,
        )

        model, mean, std = bundle
        signal = decode_audio_16k(file_bytes, file_name)
        crops = make_crops(signal)
        if not crops:
            return None
        probabilities: list[float] = []
        with torch.no_grad():
            for crop in crops:
                mel, hand = extract_crop_features(crop)
                mel_t = torch.from_numpy(mel.astype("float32")).unsqueeze(0).unsqueeze(0)
                hand_t = torch.from_numpy((hand - mean) / std).float().unsqueeze(0)
                logit = model(mel_t, hand_t)
                probabilities.append(float(torch.sigmoid(logit).item()))
        return {
            "mean_prob": sum(probabilities) / len(probabilities),
            "max_prob": max(probabilities),
            "n_crops": len(probabilities),
        }
    except Exception as exc:
        logger.warning("audio ML inference failed: %s", exc)
        return None


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


def extract_url_features(url: str, version: str = "v2") -> np.ndarray:
    """MUST remain identical to training (ml/train_models.py):
    Base (8): [length, entropy, digit_ratio, has_ip, has_at_symbol,
               suspicious_tld, http_only, num_subdomains].
    v2 additions (7): domain_in_top1m, path_shape_cat, is_uuid_like,
                      is_hex32_like, is_short_id, is_homepage, is_other.
    """
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

    base = [
        len(url),
        shannon_entropy(url),
        digit_ratio,
        1.0 if is_ip else 0.0,
        1.0 if "@" in url else 0.0,
        1.0 if tld in SUSPICIOUS_URL_TLDS else 0.0,
        1.0 if scheme == "http" else 0.0,
        float(subdomains),
    ]
    if version == "v1":
        return np.array(base, dtype=np.float64)

    from app.core.url_reputation import is_domain_in_top1m, classify_path_shape, path_shape_to_vector
    in_top1m = 1.0 if is_domain_in_top1m(host) else 0.0
    shape = classify_path_shape(parsed.path, parsed.query)
    shape_vec = path_shape_to_vector(shape)

    return np.array(base + [in_top1m] + shape_vec, dtype=np.float64)


def _image_tensor(image_bytes: bytes):
    """PIL-decode bytes -> resize 128x128 -> ToTensor -> ImageNet Normalize.

    All deepfake artifacts are 128px MobileNetV3 models (v2 onward) trained by
    ml/train_deepfake_v2.py; there is no 32px branch any more.
    """
    import torch
    from PIL import Image
    from torchvision import transforms

    transform = transforms.Compose(
        [
            transforms.Resize((128, 128)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
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
        vectorizer, model, _artifact = bundle
        proba = model.predict_proba(vectorizer.transform([text]))
        return float(proba[0][1])
    except Exception as exc:
        logger.warning("email ML inference failed: %s", exc)
        return None


def predict_url(url: str) -> float | None:
    """Probability (0-1) that the URL is malicious."""
    bundle = get_url_model()
    if bundle is None:
        return None
    try:
        model, artifact = bundle
        ver = "v2" if "v2" in artifact else "v1"
        features = extract_url_features(url, version=ver).reshape(1, -1)
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
            # Binary head class order: 0=real, 1=fake (all artifacts).
            fake_index = 1
            probability = torch.softmax(logits, dim=1)[0][fake_index]
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
