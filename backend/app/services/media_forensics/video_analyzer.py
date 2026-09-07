"""Video manipulation forensics via frame-sampled ELA (Part 5).

Samples a handful of evenly spaced frames, runs the same ELA computation
as the image analyzer on each frame, and inspects the temporal variance
of the ELA response across frames. This is a manipulation-forensics
heuristic, NOT an ML deepfake model.
"""

import os
import tempfile
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.services.media_forensics.base import MediaAnalyzer
from app.services.media_forensics.image_analyzer import compute_ela_stats

# --- Sampling and thresholds (heuristic values, not ML outputs) ---
MAX_SAMPLED_FRAMES = 10  # evenly spaced frames analyzed per video
# Mean ELA error across sampled frames above this suggests heavy local
# recompression or splicing somewhere in the video.
HIGH_MEAN_ELA_THRESHOLD = 8.0
# Variance of per-frame mean ELA above this suggests frames that were
# manipulated individually (temporal inconsistency).
TEMPORAL_VARIANCE_THRESHOLD = 20.0
# FPS outside this range is treated as abnormal container metadata.
ABNORMAL_FPS_MIN = 5.0
ABNORMAL_FPS_MAX = 120.0
# Baseline contribution to manipulation_probability before indicators.
BASE_MANIPULATION_PROBABILITY = 0.05
MAX_MANIPULATION_PROBABILITY = 0.95


class VideoAnalyzer(MediaAnalyzer):
    """Frame-sampled ELA + temporal consistency for videos."""

    method = "Frame-sampled ELA + temporal consistency"
    simulated = False

    def _sample_frames(self, video_path: str) -> tuple[list[Image.Image], float, int]:
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise ValueError("Unable to decode video stream")
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

            frames: list[Image.Image] = []
            if frame_count > 0:
                sample_indices = np.linspace(
                    0, frame_count - 1, min(MAX_SAMPLED_FRAMES, frame_count)
                ).astype(int)
                for index in sample_indices:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
                    success, frame = capture.read()
                    if success:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frames.append(Image.fromarray(rgb))
            else:
                # Unknown frame count: read sequentially and keep a spread.
                read_frames: list[Image.Image] = []
                while len(read_frames) < 100:
                    success, frame = capture.read()
                    if not success:
                        break
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    read_frames.append(Image.fromarray(rgb))
                if read_frames:
                    step = max(1, len(read_frames) // MAX_SAMPLED_FRAMES)
                    frames = read_frames[::step][:MAX_SAMPLED_FRAMES]

            if not frames:
                raise ValueError("No frames could be decoded from the video")
            return frames, fps, frame_count
        finally:
            capture.release()

    def analyze(self, file_bytes: bytes, file_name: str) -> dict[str, Any]:
        indicators: list[dict] = []
        suffix = os.path.splitext(file_name)[1] or ".mp4"

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                tmp_file.write(file_bytes)
                tmp_path = tmp_file.name

            frames, fps, frame_count = self._sample_frames(tmp_path)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("File is not a decodable video") from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        ela_stats = [compute_ela_stats(frame) for frame in frames]
        mean_ela = float(np.mean([stats["mean_error"] for stats in ela_stats]))
        temporal_variance = float(np.var([stats["mean_error"] for stats in ela_stats]))

        if mean_ela > HIGH_MEAN_ELA_THRESHOLD:
            indicators.append(
                {
                    "type": "high_mean_ela",
                    "value": f"mean_ela={mean_ela:.3f}",
                    "severity": "high",
                    "description": (
                        f"Mean ELA error across {len(frames)} sampled frames is "
                        f"high ({mean_ela:.2f}); frames were likely locally "
                        "recompressed or edited."
                    ),
                }
            )

        if temporal_variance > TEMPORAL_VARIANCE_THRESHOLD:
            indicators.append(
                {
                    "type": "temporal_inconsistency",
                    "value": f"temporal_var={temporal_variance:.3f}",
                    "severity": "high",
                    "description": (
                        "ELA response varies strongly between sampled frames; "
                        "individual frames may have been manipulated."
                    ),
                }
            )

        if frame_count <= 0:
            indicators.append(
                {
                    "type": "missing_container_metadata",
                    "value": "frame count unavailable",
                    "severity": "medium",
                    "description": (
                        "Video container does not expose a frame count; "
                        "provenance metadata is missing or non-standard."
                    ),
                }
            )

        if fps <= 0 or fps < ABNORMAL_FPS_MIN or fps > ABNORMAL_FPS_MAX:
            indicators.append(
                {
                    "type": "abnormal_fps",
                    "value": f"fps={fps:.2f}",
                    "severity": "medium",
                    "description": (
                        f"Reported frame rate {fps:.2f} fps is outside the "
                        f"expected range ({ABNORMAL_FPS_MIN}-{ABNORMAL_FPS_MAX}); "
                        "typical of re-encoded or synthesized video."
                    ),
                }
            )

        probability = BASE_MANIPULATION_PROBABILITY
        probability += min(0.5, temporal_variance / (TEMPORAL_VARIANCE_THRESHOLD * 2))
        probability += min(0.25, mean_ela / (HIGH_MEAN_ELA_THRESHOLD * 2))
        if any(indicator["type"] in {"abnormal_fps", "missing_container_metadata"} for indicator in indicators):
            probability += 0.10
        probability = min(MAX_MANIPULATION_PROBABILITY, probability)

        return self._result(1.0 - probability, probability, indicators)
