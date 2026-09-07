"""Deepfake & manipulated media detection service (Part 5 + ML Step 3).

Selects the correct forensics analyzer by content type and combines its
manipulation probability with the shared indicator-based scoring. The
analyzers are manipulation-forensics heuristics (ELA, signal statistics),
NOT ML deepfake models; the trained CNN (ml/models/deepfake_cnn.pt) is
blended in for images/videos via app/services/ml_inference.py.
"""

import logging
import os
import tempfile
from io import BytesIO
from typing import Any

from app.services.media_forensics.audio_analyzer import AudioAnalyzer
from app.services.media_forensics.base import MediaAnalyzer
from app.services.media_forensics.image_analyzer import ImageAnalyzer
from app.services.media_forensics.video_analyzer import VideoAnalyzer
from app.services.ml_inference import (
    get_deepfake_model,
    ml_indicator,
    predict_image,
    split_ml_indicator,
)
from app.services.scoring_service import calculate_score, get_severity

logger = logging.getLogger("cyberguard.deepfake")

ANALYZERS: dict[str, MediaAnalyzer] = {
    "image": ImageAnalyzer(),
    "video": VideoAnalyzer(),
    "audio": AudioAnalyzer(),
}

VIDEO_CNN_MAX_FRAMES = 5  # frames sampled for CNN inference per video


def _video_cnn_probability(file_bytes: bytes, file_name: str) -> float | None:
    """Average the CNN's fake probability over up to 5 evenly spaced frames.

    Returns None when the CNN is unavailable, the video cannot be decoded,
    or no frame yields a probability."""
    import cv2
    from PIL import Image

    if get_deepfake_model() is None:
        return None

    suffix = os.path.splitext(file_name)[1] or ".mp4"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        capture = cv2.VideoCapture(tmp_path)
        if not capture.isOpened():
            return None
        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_count <= 0:
                return None

            step = max(1, frame_count // VIDEO_CNN_MAX_FRAMES)
            probabilities: list[float] = []
            for index in range(0, frame_count, step):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                success, frame = capture.read()
                if not success:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                buffer = BytesIO()
                Image.fromarray(rgb).save(buffer, "PNG")
                probability = predict_image(buffer.getvalue())
                if probability is not None:
                    probabilities.append(probability)
                if len(probabilities) >= VIDEO_CNN_MAX_FRAMES:
                    break
            return sum(probabilities) / len(probabilities) if probabilities else None
        finally:
            capture.release()
    except Exception as exc:
        logger.warning("video CNN inference failed: %s", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def analyze_media(file_bytes: bytes, file_name: str, content_type: str) -> dict[str, Any]:
    """Run media forensics and return the unified deepfake analysis result."""
    media_type = (content_type or "").split("/", 1)[0].lower()
    analyzer = ANALYZERS.get(media_type)
    if analyzer is None:
        raise ValueError(
            f"Unsupported media content type: {content_type!r} "
            "(expected image/*, video/* or audio/*)"
        )

    result = analyzer.analyze(file_bytes, file_name)
    probability = float(result["manipulation_probability"])
    indicators = result["indicators"]

    # --- Hybrid blending (ML Step 3, monotonic safety property: the ML
    # signal may raise the ELA probability but never lower it) ---
    if media_type == "image":
        cnn_probability = predict_image(file_bytes)
        if cnn_probability is not None:
            ela_probability = probability
            probability = round(0.5 * ela_probability + 0.5 * cnn_probability, 4)
            probability = max(ela_probability, probability)
            result["authenticity_score"] = round(1.0 - probability, 4)
            indicators.append(ml_indicator("deepfake_cnn.pt", cnn_probability))
    elif media_type == "video":
        cnn_probability = _video_cnn_probability(file_bytes, file_name)
        if cnn_probability is not None:
            ela_probability = probability
            probability = round(0.5 * ela_probability + 0.5 * cnn_probability, 4)
            probability = max(ela_probability, probability)
            result["authenticity_score"] = round(1.0 - probability, 4)
            indicators.append(ml_indicator("deepfake_cnn.pt", cnn_probability))
    elif media_type == "audio":
        # Honest limitation: no trained audio model exists yet; WAV analysis
        # stays heuristic and non-WAV audio stays simulated.
        indicators.append(
            {
                "type": "ml_model",
                "value": "audio: no trained model",
                "severity": "low",
                "description": (
                    "No trained audio model exists yet; audio analysis remains "
                    "heuristic (WAV) or simulated (non-WAV)."
                ),
            }
        )

    # ML indicators document the contribution but must not add heuristic
    # weight to the score on top of the blend.
    heuristic_indicators, _ = split_ml_indicator(indicators)
    indicator_score = calculate_score(heuristic_indicators)
    risk_score = max(round(probability * 100), indicator_score)

    return {
        "module": "deepfake",
        "media_type": media_type,
        "authenticity_score": result["authenticity_score"],
        "manipulation_probability": probability,
        "indicators": indicators,
        "method": result["method"],
        "simulated": result["simulated"],
        "risk_score": risk_score,
        "severity": get_severity(risk_score),
    }
