"""Audio feature extraction for the v1 audio anti-spoofing model (Audio Step 2).

Decoding: any container (mp3, m4a, ogg, wav, flac) is decoded with
``soundfile`` first; if that fails (libsndfile has no m4a/codec support),
``torchaudio`` is tried, and finally the ``ffmpeg`` CLI as a last resort.
Everything is resampled to 16 kHz mono.

Features per 3-second crop (48000 samples @ 16 kHz, pad or trim):
  - 80-bin log-Mel spectrogram (n_fft 1024, hop 256) — the CNN branch.
  - 6 handcrafted statistics — the fused helper branch:
      1. spectral flatness (geometric/arithmetic mean of the power spectrum)
      2. spectral centroid std across frames
      3. high-frequency rolloff point (85% accumulated energy)
      4. silence ratio (frames whose RMS sits >40 dB below the loudest frame)
      5. F0 std via per-frame autocorrelation peak
      6. frame-energy kurtosis

The exact same functions serve training (ml/train_audio_v1.py via the
ml/cache/audio_v1/ shard cache) and deployment (app/services/ml_inference.py),
so inference features are identical to training features by construction.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
CROP_SECONDS = 3
CROP_SAMPLES = SAMPLE_RATE * CROP_SECONDS  # 48000
CROP_HOP_SECONDS = 1.5  # 50% overlap between consecutive crops
CROP_HOP = int(SAMPLE_RATE * CROP_HOP_SECONDS)
N_MELS = 80
N_FFT = 1024
HOP_LENGTH = 256
NORM_DB = -60.0  # dB floor for log-Mel normalisation (training + inference must match)

_MEL_FILTERBANK: np.ndarray | None = None


# ---------------------------------------------------------------------------
# Decoding + resampling
# ---------------------------------------------------------------------------

def decode_audio_16k(file_bytes: bytes, file_name: str = "") -> np.ndarray:
    """Decode any container to float32 mono at 16 kHz.

    Chain: soundfile -> torchaudio -> ffmpeg CLI. Raises ValueError when every
    backend fails so callers can skip the file with a warning.
    """
    for decoder in (_decode_soundfile, _decode_torchaudio, _decode_ffmpeg):
        try:
            decoded = decoder(file_bytes, file_name)
        except Exception:
            continue
        if decoded is not None and len(decoded[0]) > 0:
            return _resample_16k_mono(decoded)
    raise ValueError(f"no audio decoder could handle {file_name or '<bytes>'}")


def _decode_soundfile(file_bytes: bytes, file_name: str) -> tuple[np.ndarray, int]:
    import soundfile as sf

    signal, sample_rate = sf.read(io.BytesIO(file_bytes), dtype="float32", always_2d=True)
    return signal.mean(axis=1).astype(np.float32), int(sample_rate)


def _decode_torchaudio(file_bytes: bytes, file_name: str) -> tuple[np.ndarray, int]:
    import torchaudio  # optional dependency — ImportError handled by the caller

    tensor, sample_rate = torchaudio.load(io.BytesIO(file_bytes))
    return tensor.mean(dim=0).numpy().astype(np.float32), int(sample_rate)


def _decode_ffmpeg(file_bytes: bytes, file_name: str) -> tuple[np.ndarray, int]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg CLI not available")
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
        input=file_bytes,
        capture_output=True,
        check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32), SAMPLE_RATE


def _resample_16k_mono(decoded: tuple) -> np.ndarray:
    """decoded is (samples, source_rate); resample to 16 kHz mono float32."""
    signal, sample_rate = decoded
    signal = np.asarray(signal, dtype=np.float32).reshape(-1)
    if sample_rate != SAMPLE_RATE:
        from math import gcd

        import scipy.signal

        g = gcd(int(sample_rate), SAMPLE_RATE)
        signal = scipy.signal.resample_poly(signal, SAMPLE_RATE // g, int(sample_rate) // g)
    return np.nan_to_num(signal.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def decode_wav_stdlib(file_bytes: bytes) -> tuple[np.ndarray, int]:
    """Standard-library WAV decode (fast path for 16-bit PCM WAV uploads)."""
    with wave.open(io.BytesIO(file_bytes)) as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("only 16-bit PCM WAV supported by the fast path")
        channels = wav_file.getnchannels()
        rate = wav_file.getframerate()
        raw = wav_file.readframes(wav_file.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return (samples.astype(np.float32) / 32768.0), int(rate)


# ---------------------------------------------------------------------------
# Mel filterbank (numpy, deterministic — no librosa dependency)
# ---------------------------------------------------------------------------

def _hz_to_mel(freq: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + freq / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def mel_filterbank() -> np.ndarray:
    """[N_MELS, N_FFT//2+1] triangular filterbank on 0..8000 Hz."""
    global _MEL_FILTERBANK
    if _MEL_FILTERBANK is not None:
        return _MEL_FILTERBANK
    freqs = np.linspace(0, SAMPLE_RATE / 2, N_FFT // 2 + 1)
    mel_pts = _mel_to_hz(
        np.linspace(_hz_to_mel(np.array([0.0]))[0], _hz_to_mel(np.array([SAMPLE_RATE / 2]))[0], N_MELS + 2)
    )
    bank = np.zeros((N_MELS, len(freqs)), dtype=np.float32)
    for i in range(N_MELS):
        left, center, right = mel_pts[i], mel_pts[i + 1], mel_pts[i + 2]
        up = (freqs - left) / max(center - left, 1e-10)
        down = (right - freqs) / max(right - center, 1e-10)
        bank[i] = np.clip(np.minimum(up, down), 0.0, None)
    _MEL_FILTERBANK = bank
    return bank


# ---------------------------------------------------------------------------
# Crops
# ---------------------------------------------------------------------------

def make_crops(signal: np.ndarray, max_crops: int | None = None) -> list[np.ndarray]:
    """3-second crops with 50% overlap; pad a short signal with zeros."""
    signal = np.asarray(signal, dtype=np.float32)
    if len(signal) == 0:
        return []
    if len(signal) <= CROP_SAMPLES:
        padded = np.zeros(CROP_SAMPLES, dtype=np.float32)
        padded[: len(signal)] = signal
        return [padded]
    crops: list[np.ndarray] = []
    start = 0
    while True:
        window = signal[start : start + CROP_SAMPLES]
        if len(window) >= CROP_SAMPLES // 2:
            padded = np.zeros(CROP_SAMPLES, dtype=np.float32)
            padded[: len(window)] = window
            crops.append(padded)
        if start + CROP_SAMPLES >= len(signal):
            break
        start += CROP_HOP
        if max_crops and len(crops) >= max_crops:
            break
    if max_crops:
        crops = crops[:max_crops]
    return crops


# ---------------------------------------------------------------------------
# Feature extraction (identical for training and inference)
# ---------------------------------------------------------------------------

def logmel_80(signal: np.ndarray) -> np.ndarray:
    """[80, T] normalised log-Mel for one 3s crop (T = 1 + (CROP_SAMPLES-N_FFT)//HOP+1)."""
    frames = 1 + (len(signal) - N_FFT) // HOP_LENGTH if len(signal) >= N_FFT else 0
    if frames <= 0:
        padded = np.zeros(N_FFT, dtype=np.float32)
        padded[: len(signal)] = signal
        signal = padded
        frames = 1
    windowed = np.stack(
        [signal[i * HOP_LENGTH : i * HOP_LENGTH + N_FFT] * np.hanning(N_FFT) for i in range(frames)]
    )
    magnitude = np.abs(np.fft.rfft(windowed, axis=1)) ** 2  # power spectrogram [T, F]
    mel = magnitude @ mel_filterbank().T + 1e-10
    logmel = 10.0 * np.log10(mel)
    floor = logmel.max() + NORM_DB
    return np.maximum(logmel, floor).T.astype(np.float32)  # [80, T]


def _frame_slices(signal: np.ndarray, frame: int = 1024, hop: int = 512) -> list[np.ndarray]:
    count = max(1, (len(signal) - frame) // hop + 1) if len(signal) >= frame else 1
    if len(signal) < frame:
        return [np.pad(signal, (0, frame - len(signal)))]
    return [signal[i * hop : i * hop + frame] for i in range(count)]


def handcrafted_features(signal: np.ndarray) -> np.ndarray:
    """6 handcrafted statistics, returned as float32[6] in training order."""
    windowed = signal * np.hanning(len(signal))
    spectrum = np.abs(np.fft.rfft(windowed)) ** 2 + 1e-12
    freqs = np.linspace(0, SAMPLE_RATE / 2, len(spectrum))

    # 1. spectral flatness
    flatness = float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))

    # 2-3. per-frame spectral centroid std + rolloff
    frames = _frame_slices(signal)
    centroids, rolloffs, energies, f0s = [], [], [], []
    total_energy = float(spectrum.sum())
    cumulative = np.cumsum(spectrum)
    rolloff = float(freqs[np.searchsorted(cumulative, 0.85 * total_energy)])
    for fr in frames:
        spec = np.abs(np.fft.rfft(fr * np.hanning(len(fr)))) ** 2 + 1e-12
        fr_freqs = np.linspace(0, SAMPLE_RATE / 2, len(spec))
        centroids.append(float((spec * fr_freqs).sum() / spec.sum()))
        cumulative_fr = np.cumsum(spec)
        rolloffs.append(float(fr_freqs[np.searchsorted(cumulative_fr, 0.85 * spec.sum())]))
        rms = float(np.sqrt(np.mean(fr**2)) + 1e-12)
        energies.append(rms)
        # F0 via autocorrelation peak in the 60-400 Hz lag band (voiced frames)
        ac = np.correlate(fr, fr, mode="full")[len(fr) - 1 :]
        ac = ac / (ac[0] + 1e-12)
        lo, hi = int(SAMPLE_RATE / 400), int(SAMPLE_RATE / 60)
        if hi < len(ac) and ac[lo:hi].max() > 0.35:
            f0s.append(SAMPLE_RATE / (lo + int(ac[lo:hi].argmax())))

    centroid_std = float(np.std(centroids))
    rolloff_mean = float(np.mean(rolloffs))

    energies_db = 20.0 * np.log10(np.array(energies) + 1e-12)
    silence_ratio = float(np.mean(energies_db < (energies_db.max() - 40.0)))

    f0_std = float(np.std(f0s)) if len(f0s) >= 2 else 0.0

    e = np.array(energies)
    energy_kurtosis = float(
        np.mean((e - e.mean()) ** 4) / (e.std() ** 4 + 1e-12) if len(e) > 1 else 0.0
    )

    return np.array(
        [flatness, centroid_std, rolloff_mean, silence_ratio, f0_std, energy_kurtosis],
        dtype=np.float32,
    )


def extract_crop_features(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Features for ONE 3s crop: (logmel [80,T] float32, handcrafted float32[6])."""
    return logmel_80(signal), handcrafted_features(signal)


HANDCRAFT_DIM = 6
HANDCRAFT_NAMES = [
    "spectral_flatness",
    "spectral_centroid_std",
    "hf_rolloff",
    "silence_ratio",
    "f0_std",
    "frame_energy_kurtosis",
]
