"""Image manipulation forensics via Error Level Analysis (Part 5).

ELA is a manipulation-forensics heuristic, NOT an ML deepfake model: the
image is re-encoded at a fixed JPEG quality and the per-pixel residual
error is inspected. Spliced or locally recompressed regions respond
differently to re-encoding than the rest of the image, which shows up as
block-level variance in the error map.
"""

import io
from typing import Any

import numpy as np
from PIL import Image

from app.services.media_forensics.base import MediaAnalyzer

# --- ELA parameters and thresholds (heuristic values, not ML outputs) ---
# JPEG quality used for the reference re-encoding; lower quality amplifies
# the residual in edited regions more strongly.
ELA_JPEG_QUALITY = 90
# Variance of the per-8x8-block mean error above this value suggests a
# locally spliced/recompressed region sitting inside a cleaner image.
# Calibrated against scripts/make_test_media.py output (benign gradient
# ~0.006, spliced gradient ~0.014); real photos need per-dataset tuning.
HIGH_BLOCK_VARIANCE_THRESHOLD = 0.010
# An error map that is almost flat everywhere (very low mean AND variance)
# suggests the image was regenerated wholesale (e.g. AI-generated) rather
# than edited.
UNIFORM_ERROR_MEAN_MAX = 0.2
UNIFORM_ERROR_VARIANCE_MAX = 0.005
# Baseline contribution to manipulation_probability before indicators.
BASE_MANIPULATION_PROBABILITY = 0.05
# How strongly block variance pushes the probability, capped.
BLOCK_VARIANCE_PROBABILITY_CAP = 0.55
# Extra probability weight for a container mismatch (strong tamper signal).
CONTAINER_MISMATCH_PROBABILITY = 0.20
# Extra probability weight for a fully uniform error map.
UNIFORM_ERROR_PROBABILITY = 0.10
# Maximum probability any analyzer may emit.
MAX_MANIPULATION_PROBABILITY = 0.95

# Recognized image file extensions mapped to the format Pillow reports.
EXTENSION_TO_FORMAT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "bmp": "BMP",
    "gif": "GIF",
    "tiff": "TIFF",
    "tif": "TIFF",
}

BLOCK_SIZE = 8


def compute_ela_stats(image: Image.Image) -> dict[str, float]:
    """Compute ELA statistics for a PIL image.

    Re-encodes the image as JPEG at ELA_JPEG_QUALITY, takes the per-pixel
    absolute difference and returns the mean error, max error and the
    variance of the per-8x8-block mean error.
    """
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=ELA_JPEG_QUALITY)
    buffer.seek(0)

    original = np.asarray(image.convert("RGB"), dtype=np.float64)
    reencoded = np.asarray(Image.open(buffer).convert("RGB"), dtype=np.float64)
    error_map = np.abs(original - reencoded).mean(axis=2)

    height, width = error_map.shape
    cropped_h = height - (height % BLOCK_SIZE)
    cropped_w = width - (width % BLOCK_SIZE)
    if cropped_h == 0 or cropped_w == 0:
        block_variance = 0.0
    else:
        blocks = (
            error_map[:cropped_h, :cropped_w]
            .reshape(cropped_h // BLOCK_SIZE, BLOCK_SIZE, cropped_w // BLOCK_SIZE, BLOCK_SIZE)
            .mean(axis=(1, 3))
        )
        block_variance = float(blocks.var())

    return {
        "mean_error": float(error_map.mean()),
        "max_error": float(error_map.max()),
        "block_variance": block_variance,
    }


class ImageAnalyzer(MediaAnalyzer):
    """ELA + metadata forensics for single images."""

    method = "Error Level Analysis (ELA) + metadata forensics"
    simulated = False

    def analyze(self, file_bytes: bytes, file_name: str) -> dict[str, Any]:
        indicators: list[dict] = []

        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.load()
        except Exception as exc:
            raise ValueError("File is not a decodable image") from exc

        actual_format = (image.format or "").upper()
        extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        expected_format = EXTENSION_TO_FORMAT.get(extension)
        container_mismatch = bool(expected_format and expected_format != actual_format)
        if container_mismatch:
            indicators.append(
                {
                    "type": "container_mismatch",
                    "value": f"extension .{extension} but decoded as {actual_format}",
                    "severity": "high",
                    "description": (
                        f"File extension suggests {expected_format} but the decoded "
                        f"container is {actual_format}; the file may have been "
                        "re-wrapped to hide its origin."
                    ),
                }
            )

        if not image.info.get("exif"):
            indicators.append(
                {
                    "type": "missing_exif",
                    "value": "no EXIF metadata present",
                    "severity": "low",
                    "description": (
                        "Image carries no EXIF metadata; original camera or "
                        "software provenance information is absent (common in "
                        "processed or generated images)."
                    ),
                }
            )

        stats = compute_ela_stats(image)

        uniform_error_map = (
            stats["mean_error"] < UNIFORM_ERROR_MEAN_MAX
            and stats["block_variance"] < UNIFORM_ERROR_VARIANCE_MAX
        )
        if uniform_error_map:
            indicators.append(
                {
                    "type": "uniform_error_map",
                    "value": f"mean={stats['mean_error']:.3f}, block_var={stats['block_variance']:.4f}",
                    "severity": "medium",
                    "description": (
                        "ELA error map is unusually uniform; the image may have "
                        "been regenerated wholesale rather than edited."
                    ),
                }
            )
        elif stats["block_variance"] > HIGH_BLOCK_VARIANCE_THRESHOLD:
            indicators.append(
                {
                    "type": "high_block_variance",
                    "value": f"block_var={stats['block_variance']:.3f}",
                    "severity": "high",
                    "description": (
                        "ELA block error variance is high; part of the image was "
                        "likely spliced or locally recompressed."
                    ),
                }
            )

        probability = BASE_MANIPULATION_PROBABILITY
        # Cubic scaling keeps sub-threshold variance (clean images) near the
        # baseline while pushing clear splices towards the cap.
        probability += min(
            BLOCK_VARIANCE_PROBABILITY_CAP,
            (stats["block_variance"] / HIGH_BLOCK_VARIANCE_THRESHOLD) ** 3
            * BLOCK_VARIANCE_PROBABILITY_CAP,
        )
        if container_mismatch:
            probability += CONTAINER_MISMATCH_PROBABILITY
        if uniform_error_map:
            probability += UNIFORM_ERROR_PROBABILITY
        probability = min(MAX_MANIPULATION_PROBABILITY, probability)

        return self._result(1.0 - probability, probability, indicators)
