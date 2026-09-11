"""Deepfake & manipulated media detection service (Part 5 + ML Step 3).

Selects the correct forensics analyzer by content type and combines its
manipulation probability with the shared indicator-based scoring. The
analyzers are manipulation-forensics heuristics (ELA, signal statistics);
the single neural model (deepfake_cnn_v2.pt — MobileNetV3-Small on GenImage,
selected by ml/models/calibration.json) is blended in for images/videos via
app/services/ml_inference.py. When the neural artifact is unavailable the
detector degrades to heuristics-only with an explicit
"heuristics-only-fallback" ml_model indicator — there is no neural fallback
and no manipulation cap (the old v1 cap was deleted with the v1 artifact).
"""

import logging
import os
import tempfile
from io import BytesIO
from typing import Any

from app.services.media_forensics.audio_analyzer import AudioAnalyzer, _is_wav
from app.services.media_forensics.base import MediaAnalyzer
from app.services.media_forensics.image_analyzer import ImageAnalyzer
from app.services.media_forensics.video_analyzer import VideoAnalyzer
from app.services.ml_inference import (
    AUDIO_ARTIFACT,
    audio_model_available,
    deepfake_degraded,
    deepfake_model_artifact,
    get_deepfake_model,
    ml_indicator,
    predict_audio,
    predict_image,
    split_ml_indicator,
)
from app.core.calibration import get_deepfake_calibration
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


def _extract_splice_score(result: dict[str, Any], indicators: list[dict]) -> float:
    if "splice_score" in result:
        try:
            return float(result["splice_score"])
        except (ValueError, TypeError):
            pass
    for ind in indicators:
        val = str(ind.get("value", ""))
        if "splice_score=" in val:
            try:
                part = val.split("splice_score=")[1].split(",")[0].strip()
                return float(part)
            except (ValueError, IndexError):
                pass
    return 0.0


def analyze_media(file_bytes: bytes, file_name: str, content_type: str) -> dict[str, Any]:
    """Run media forensics and return the unified deepfake analysis result.

    There is exactly ONE neural artifact (the 128px model selected by
    ml/models/calibration.json). When it is unavailable the detector degrades
    to heuristics-only (ELA splice + metadata) with an explicit
    "heuristics-only-fallback" ml_model indicator — there is no neural
    fallback and no manipulation cap.
    """
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

    calib = get_deepfake_calibration()
    cnn_real_threshold = float(calib.get("cnn_real_threshold", 0.10))
    strong_splice_threshold = float(calib.get("strong_splice_threshold", 4.0))
    weak_splice_manipulation_cap = float(calib.get("weak_splice_manipulation_cap", 0.35))
    manipulation_cap_without_splice = float(calib.get("manipulation_cap_without_splice", 0.35))

    splice_score = _extract_splice_score(result, indicators)
    has_splice_indicator = any(i.get("type") == "high_block_variance" for i in indicators)
    cnn_probability = None

    # --- Hybrid blending with CNN vs ELA disagreement policy ---
    if media_type == "image":
        cnn_probability = predict_image(file_bytes)
        if cnn_probability is not None:
            indicators.append(ml_indicator(deepfake_model_artifact(), cnn_probability))
            if cnn_probability < cnn_real_threshold:
                if splice_score < strong_splice_threshold:
                    effective_cap = weak_splice_manipulation_cap if has_splice_indicator else manipulation_cap_without_splice
                    probability = min(probability, effective_cap)
                    for ind in indicators:
                        if ind.get("type") == "high_block_variance":
                            ind["type"] = "ela_weak_splice_unconfirmed"
                            ind["severity"] = "low"
                            ind["description"] = (
                                "localized ELA residual not confirmed by the neural model; "
                                "consistent with messenger cropping or filters; monitor only"
                            )
                else:
                    for ind in indicators:
                        if ind.get("type") == "high_block_variance":
                            ind["description"] = (
                                f"Strong localized ELA residual (splice_score={splice_score:.2f} >= {strong_splice_threshold}) "
                                f"overrides neural prediction (prob={cnn_probability:.4f}); "
                                "likely localized splice or manipulation."
                            )
            else:
                ela_probability = probability
                probability = round(0.5 * ela_probability + 0.5 * cnn_probability, 4)
                probability = max(ela_probability, probability)
        elif deepfake_degraded():
            logger.warning(
                "deepfake neural model unavailable — heuristics-only fallback "
                "for %s (ELA/metadata only)",
                file_name,
            )
            indicators.append(
                {
                    "type": "ml_model",
                    "value": "heuristics-only-fallback",
                    "severity": "low",
                    "description": (
                        "Neural deepfake model unavailable; probability comes "
                        "from ELA/metadata heuristics only."
                    ),
                }
            )
    elif media_type == "video":
        cnn_probability = _video_cnn_probability(file_bytes, file_name)
        if cnn_probability is not None:
            indicators.append(ml_indicator(deepfake_model_artifact(), cnn_probability))
            if cnn_probability < cnn_real_threshold:
                if splice_score < strong_splice_threshold:
                    effective_cap = weak_splice_manipulation_cap if has_splice_indicator else manipulation_cap_without_splice
                    probability = min(probability, effective_cap)
                    for ind in indicators:
                        if ind.get("type") == "high_block_variance":
                            ind["type"] = "ela_weak_splice_unconfirmed"
                            ind["severity"] = "low"
                            ind["description"] = (
                                "localized ELA residual not confirmed by the neural model; "
                                "consistent with messenger cropping or filters; monitor only"
                            )
                else:
                    for ind in indicators:
                        if ind.get("type") == "high_block_variance":
                            ind["description"] = (
                                f"Strong localized ELA residual (splice_score={splice_score:.2f} >= {strong_splice_threshold}) "
                                f"overrides neural prediction (prob={cnn_probability:.4f}); "
                                "likely localized splice or manipulation."
                            )
            else:
                ela_probability = probability
                probability = round(0.5 * ela_probability + 0.5 * cnn_probability, 4)
                probability = max(ela_probability, probability)
        elif deepfake_degraded():
            logger.warning(
                "deepfake neural model unavailable — heuristics-only fallback "
                "for video %s",
                file_name,
            )
            indicators.append(
                {
                    "type": "ml_model",
                    "value": "heuristics-only-fallback",
                    "severity": "low",
                    "description": (
                        "Neural deepfake model unavailable; probability comes "
                        "from ELA/metadata heuristics only."
                    ),
                }
            )
    elif media_type == "audio":
        # Trained audio anti-spoofing model (audio_cnn_v1.pt): when it loads,
        # real forensic inference replaces the simulated hash score —
        #   WAV inputs:  manipulation = 0.6 * model_prob + 0.4 * WAV heuristics
        #   non-WAV:     manipulation = model_prob (heuristics cannot decode it)
        # with the monotonic max() rule against the heuristic probability so a
        # trained model can raise but never lower the heuristic verdict.
        # When the model is unavailable the simulated hash path stays exactly
        # as before (simulated=True, reserved-model-hook indicator).
        heuristic_probability = probability
        audio_prediction = predict_audio(file_bytes, file_name)
        if audio_prediction is not None:
            # Flag on the max crop: the probability carried by the ml_model
            # indicator is the highest single-crop fake probability (the mean
            # is kept as detail). The blended score always uses this value.
            model_prob = float(audio_prediction["max_prob"])
            indicators.append(
                ml_indicator(AUDIO_ARTIFACT, model_prob)
                | {"detail": {"mean_crop_prob": round(audio_prediction["mean_prob"], 4), "n_crops": audio_prediction["n_crops"]}}
            )
            if _is_wav(file_bytes):
                probability = round(0.6 * model_prob + 0.4 * heuristic_probability, 4)
                probability = max(heuristic_probability, probability)
                result["method"] = "LCNN log-Mel CNN (audio_cnn_v1) + WAV signal statistics"
            else:
                probability = round(model_prob, 4)
                probability = max(heuristic_probability, probability)
                result["method"] = "LCNN log-Mel CNN (audio_cnn_v1) crop inference"
            result["simulated"] = False
            # Applicability gate: the model is a VOICE anti-spoofing CNN
            # (ASVspoof speech); when the WAV forensics show a synthetic
            # non-speech tone (constant ZCR / purely tonal spectrum) its
            # verdict is out of domain — cap the model's contribution
            # (never below the heuristic verdict) and mark it low.
            non_speech_tone = any(
                ind.get("type") in ("constant_zero_crossing_rate", "purely_tonal_spectrum")
                for ind in indicators
            )
            if non_speech_tone:
                tone_cap = float(calib.get("audio_tone_manipulation_cap", 0.35))
                probability = max(heuristic_probability, min(probability, tone_cap))
                for ind in indicators:
                    if ind.get("type") == "ml_model" and ind.get("value") == AUDIO_ARTIFACT:
                        ind["severity"] = "low"
                        ind["description"] = (
                            "Trained voice-spoofing model probability: "
                            f"{model_prob:.2f}, but the clip is a synthetic "
                            "non-speech tone (constant zero-crossing rate / "
                            "purely tonal spectrum) — outside the model's "
                            "speech domain, so its contribution is capped."
                        )
        else:
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

    result["authenticity_score"] = round(1.0 - probability, 4)
    result["manipulation_probability"] = probability

    # ML indicators document the contribution but must not add heuristic
    # weight to the score on top of the blend.
    heuristic_indicators, _ = split_ml_indicator(indicators)
    indicator_score = calculate_score(heuristic_indicators)
    risk_score = max(round(probability * 100), indicator_score)

    if media_type in ("image", "video") and cnn_probability is not None and cnn_probability < cnn_real_threshold:
        if splice_score < strong_splice_threshold:
            risk_score = min(40, risk_score)

    severity = get_severity(risk_score)

    return {
        "module": "deepfake",
        "media_type": media_type,
        "authenticity_score": result["authenticity_score"],
        "manipulation_probability": probability,
        "indicators": indicators,
        "method": result["method"],
        "simulated": result["simulated"],
        "risk_score": risk_score,
        "severity": severity,
    }
