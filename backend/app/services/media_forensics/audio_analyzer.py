"""Audio forensics analyzer (Part 5).

For WAV files this performs REAL signal statistics with the standard
library wave module and numpy: clipping ratio, zero-crossing rate
variance and a spectral flatness proxy via FFT. These are
manipulation-forensics heuristics, NOT an ML deepfake model.

For non-WAV audio the analysis is explicitly SIMULATED: indicators and
scores are derived deterministically from the SHA-256 of the bytes so
results are reproducible, and `simulated` is True. A Hugging Face audio
model hook is reserved for later parts.
"""

import hashlib
import io
import wave
from typing import Any

import numpy as np

from app.services.media_forensics.base import MediaAnalyzer

# --- WAV signal thresholds (heuristic values, not ML outputs) ---
# Fraction of samples at/above 99.9% full scale above which the signal is
# considered clipped.
CLIPPING_RATIO_THRESHOLD = 0.02
CLIPPING_AMPLITUDE_FRACTION = 0.999
# Window size (samples) for per-window zero-crossing rate measurement.
ZCR_WINDOW_SIZE = 1024
# Variance of per-window ZCR below this means the pitch structure is
# essentially constant, a signature of synthetic tones.
ZCR_VARIANCE_LOW_THRESHOLD = 1e-4
# Number of spectral bands used for the hole detection proxy.
SPECTRAL_BAND_COUNT = 32
# Bands more than this many dB below the loudest band count as holes.
SPECTRAL_HOLE_DB_FLOOR = 60.0
# Fraction of holes above which the spectrum is considered gapped.
SPECTRAL_HOLE_RATIO_THRESHOLD = 0.6
# Spectral flatness proxy below this means a purely tonal signal.
FLATNESS_TONAL_MAX = 0.05

# --- Simulated (non-WAV) scoring bounds ---
SIMULATED_BASE_PROBABILITY = 0.10
SIMULATED_PROBABILITY_SPAN = 0.55

# Baseline contribution to manipulation_probability before indicators.
BASE_MANIPULATION_PROBABILITY = 0.05
MAX_MANIPULATION_PROBABILITY = 0.95


def _is_wav(file_bytes: bytes) -> bool:
    return file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WAVE"


def _analyze_wav(file_bytes: bytes) -> tuple[list[dict], float]:
    """Real WAV signal statistics. Returns (indicators, manipulation_probability)."""
    with wave.open(io.BytesIO(file_bytes)) as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        raw_frames = wav_file.readframes(frame_count)

    if sample_width != 2 or channels < 1 or frame_count == 0:
        raise ValueError(
            "Unsupported WAV format: 16-bit PCM with at least one channel is required"
        )

    samples = np.frombuffer(raw_frames, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    signal = samples.astype(np.float64) / 32768.0

    indicators: list[dict] = []

    # 1. Clipping ratio: samples at or above 99.9% full scale.
    clipping_ratio = float(np.mean(np.abs(samples) >= 32767 * CLIPPING_AMPLITUDE_FRACTION))
    if clipping_ratio > CLIPPING_RATIO_THRESHOLD:
        indicators.append(
            {
                "type": "audio_clipping",
                "value": f"clipping_ratio={clipping_ratio:.4f}",
                "severity": "high",
                "description": (
                    f"{clipping_ratio * 100:.1f}% of samples are at full scale "
                    "(threshold 2%); the waveform is clipped, typical of mixed "
                    "or spliced audio."
                ),
            }
        )

    # 2. Zero-crossing rate variance across windows.
    window_count = len(signal) // ZCR_WINDOW_SIZE
    zcr_variance = 0.0
    if window_count >= 2:
        windows = signal[: window_count * ZCR_WINDOW_SIZE].reshape(
            window_count, ZCR_WINDOW_SIZE
        )
        zero_crossings = np.sum(np.abs(np.diff(np.sign(windows), axis=1)) > 0, axis=1)
        zcr_rates = zero_crossings / ZCR_WINDOW_SIZE
        zcr_variance = float(np.var(zcr_rates))
        if zcr_variance < ZCR_VARIANCE_LOW_THRESHOLD:
            indicators.append(
                {
                    "type": "constant_zero_crossing_rate",
                    "value": f"zcr_variance={zcr_variance:.2e}",
                    "severity": "medium",
                    "description": (
                        "Zero-crossing rate is nearly constant across the clip, "
                        "a signature of synthetic tones rather than natural audio."
                    ),
                }
            )

    # 3. Spectral flatness proxy (geometric mean / arithmetic mean) and
    #    spectral hole detection on log-spaced-equal band energies.
    windowed = signal * np.hanning(len(signal))
    magnitude = np.abs(np.fft.rfft(windowed)) + 1e-12
    flatness = float(np.exp(np.mean(np.log(magnitude))) / np.mean(magnitude))

    band_edges = np.linspace(0, len(magnitude), SPECTRAL_BAND_COUNT + 1).astype(int)
    band_power_db = np.array(
        [
            10 * np.log10(float(magnitude[start:stop].mean() ** 2) + 1e-20)
            if stop > start
            else -200.0
            for start, stop in zip(band_edges[:-1], band_edges[1:])
        ]
    )
    hole_ratio = float(
        np.mean(band_power_db < (band_power_db.max() - SPECTRAL_HOLE_DB_FLOOR))
    )
    if hole_ratio > SPECTRAL_HOLE_RATIO_THRESHOLD:
        indicators.append(
            {
                "type": "spectral_holes",
                "value": f"hole_ratio={hole_ratio:.2f}",
                "severity": "medium",
                "description": (
                    f"{hole_ratio * 100:.0f}% of spectral bands sit far below the "
                    "dominant band; energy gaps can indicate synthesized or "
                    "spliced content."
                ),
            }
        )
    if flatness < FLATNESS_TONAL_MAX:
        indicators.append(
            {
                "type": "purely_tonal_spectrum",
                "value": f"flatness={flatness:.4f}",
                "severity": "low",
                "description": (
                    "Spectral flatness proxy is near zero: the clip is dominated "
                    "by a single tone rather than a natural broadband spectrum."
                ),
            }
        )

    probability = BASE_MANIPULATION_PROBABILITY
    if clipping_ratio > CLIPPING_RATIO_THRESHOLD:
        probability += 0.40
    if hole_ratio > SPECTRAL_HOLE_RATIO_THRESHOLD:
        probability += 0.20
    if zcr_variance < ZCR_VARIANCE_LOW_THRESHOLD and window_count >= 2:
        probability += 0.15
    probability = min(MAX_MANIPULATION_PROBABILITY, probability)
    return indicators, probability


def _analyze_simulated(file_bytes: bytes) -> tuple[list[dict], float]:
    """Deterministic hash-derived result for non-WAV audio (simulated=True)."""
    digest = hashlib.sha256(file_bytes).hexdigest()
    seed = int(digest[:8], 16)
    probability = SIMULATED_BASE_PROBABILITY + (seed % 100) / 100 * SIMULATED_PROBABILITY_SPAN
    indicators = [
        {
            "type": "simulated_audio_analysis",
            "value": f"sha256:{digest[:16]}",
            "severity": "medium",
            "description": (
                "Non-WAV audio cannot be analyzed locally in this part; the "
                "score below is SIMULATED and derived deterministically from "
                "the file hash. A Hugging Face audio model hook is reserved."
            ),
        }
    ]
    return indicators, probability


class AudioAnalyzer(MediaAnalyzer):
    """WAV signal statistics / simulated analysis for other audio formats."""

    method = "Signal statistics (clipping, ZCR variance, spectral flatness)"
    simulated = False

    def analyze(self, file_bytes: bytes, file_name: str) -> dict[str, Any]:
        if _is_wav(file_bytes):
            indicators, probability = _analyze_wav(file_bytes)
            return self._result(1.0 - probability, probability, indicators)
        indicators, probability = _analyze_simulated(file_bytes)
        return self._result(
            1.0 - probability,
            probability,
            indicators,
            method="Simulated spectral analysis (model hook reserved)",
            simulated=True,
        )
