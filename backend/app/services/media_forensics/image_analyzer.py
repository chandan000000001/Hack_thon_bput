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

from app.core.calibration import get_deepfake_calibration
from app.services.media_forensics.base import MediaAnalyzer

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


def compute_ela_stats(image: Image.Image, calib: dict[str, Any] | None = None) -> dict[str, float]:
    """Compute ELA statistics for a PIL image using calibration thresholds.

    Re-encodes the image as JPEG at calibrated quality, takes the per-pixel
    absolute difference, computes block errors, and evaluates median block
    error m, top-5% mean t, and splice_score = t/m.
    """
    if calib is None:
        calib = get_deepfake_calibration()

    jpeg_quality = int(calib.get("jpeg_quality", 90))
    block_size = int(calib.get("block_size", 8))
    noise_floor = float(calib.get("noise_floor", 0.55))
    top_percent = float(calib.get("top_percent", 0.05))
    bot_blocks_cap = int(calib.get("bot_blocks_cap", 32))

    rgb_image = image.convert("RGB") if image.mode != "RGB" else image
    buffer = io.BytesIO()
    rgb_image.save(buffer, "JPEG", quality=jpeg_quality)
    buffer.seek(0)

    original = np.asarray(rgb_image, dtype=np.float64)
    reencoded = np.asarray(Image.open(buffer).convert("RGB"), dtype=np.float64)
    error_map = np.abs(original - reencoded).mean(axis=2)

    height, width = error_map.shape
    cropped_h = height - (height % block_size)
    cropped_w = width - (width % block_size)
    if cropped_h == 0 or cropped_w == 0:
        return {
            "mean_error": float(error_map.mean()) if error_map.size > 0 else 0.0,
            "max_error": float(error_map.max()) if error_map.size > 0 else 0.0,
            "block_variance": 0.0,
            "splice_score": 0.0,
            "median_block_error": 0.0,
            "top5_mean_error": 0.0,
        }

    blocks = (
        error_map[:cropped_h, :cropped_w]
        .reshape(cropped_h // block_size, block_size, cropped_w // block_size, block_size)
        .mean(axis=(1, 3))
    ).flatten()
    block_variance = float(blocks.var())
    m = float(np.median(blocks))
    eff_m = max(m, noise_floor)
    k = max(1, int(len(blocks) * top_percent))
    sorted_blocks = np.sort(blocks)
    t = float(np.mean(sorted_blocks[-k:]))
    top_ratio = t / eff_m

    actual_format = (getattr(image, "format", "") or "").upper()
    bot_ratio = 0.0
    if actual_format != "JPEG":
        k_bot = max(1, min(k, bot_blocks_cap))
        nz = sorted_blocks[sorted_blocks > 0.02]
        if len(nz) >= k_bot:
            b = float(np.mean(nz[:k_bot]))
            if b > 0.01:
                bot_ratio = eff_m / b

    splice_score = float(max(top_ratio, bot_ratio))

    return {
        "mean_error": float(error_map.mean()),
        "max_error": float(error_map.max()),
        "block_variance": block_variance,
        "splice_score": splice_score,
        "median_block_error": m,
        "top5_mean_error": t,
    }


class ImageAnalyzer(MediaAnalyzer):
    """ELA + metadata forensics for single images."""

    method = "Error Level Analysis (ELA) + metadata forensics"
    simulated = False

    def analyze(self, file_bytes: bytes, file_name: str) -> dict[str, Any]:
        calib = get_deepfake_calibration()
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
                    "severity": calib.get("missing_exif_severity", "low"),
                    "description": (
                        "Image carries no EXIF metadata; expected after messenger recompression "
                        "or synthetic generation."
                    ),
                }
            )

        stats = compute_ela_stats(image, calib)

        uniform_mean_max = float(calib.get("uniform_error_mean_max", 0.2))
        uniform_var_max = float(calib.get("uniform_error_variance_max", 0.005))
        splice_score_threshold = float(calib.get("splice_score_threshold", 3.0))
        global_recomp_threshold = float(calib.get("global_recompression_mean_threshold", 0.2))

        uniform_error_map = (
            stats["mean_error"] < uniform_mean_max
            and stats["block_variance"] < uniform_var_max
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
        elif stats["splice_score"] > splice_score_threshold:
            # Emit high_block_variance ONLY when splice_score > 3.0
            indicators.append(
                {
                    "type": "high_block_variance",
                    "value": f"splice_score={stats['splice_score']:.2f}, block_var={stats['block_variance']:.3f}",
                    "severity": "high",
                    "description": (
                        "ELA block error variance is high; part of the image was "
                        "likely spliced or locally recompressed."
                    ),
                }
            )
        elif stats["mean_error"] >= global_recomp_threshold:
            # Otherwise, if mean error is uniformly elevated, emit global_recompression
            indicators.append(
                {
                    "type": "global_recompression",
                    "value": f"mean={stats['mean_error']:.3f}, splice_score={stats['splice_score']:.2f}",
                    "severity": calib.get("global_recompression_severity", "low"),
                    "description": (
                        "Uniformly elevated ELA residual consistent with WhatsApp/JPEG "
                        "messenger recompression without localised tampering."
                    ),
                }
            )

        probability = float(calib.get("base_manipulation_probability", 0.05))
        if stats["splice_score"] > splice_score_threshold:
            probability_cap = float(calib.get("block_variance_probability_cap", 0.55))
            ratio = stats["splice_score"] / splice_score_threshold
            probability += min(probability_cap, (ratio ** 2) * 0.40)

        if container_mismatch:
            probability += float(calib.get("container_mismatch_probability", 0.20))
        if uniform_error_map:
            probability += float(calib.get("uniform_error_probability", 0.10))

        max_prob = float(calib.get("max_manipulation_probability", 0.95))
        probability = min(max_prob, probability)

        res = self._result(1.0 - probability, probability, indicators)
        res["splice_score"] = stats["splice_score"]
        return res
