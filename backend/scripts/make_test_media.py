"""Generate test media for the deepfake forensics module (Part 5).

Outputs into <project root>/evidence/media/:
- benign.png: a smooth 256x256 RGB gradient (clean reference image). A
  subtle sinusoidal ripple keeps the gradient smooth to the eye while
  giving JPEG quantizers mid-frequency content to react to.
- manipulated.png: the same gradient with a 64x64 region replaced by a
  separately JPEG-compressed copy, producing an ELA discontinuity that
  the image analyzer should flag as high block variance.
- tone.wav: a 1 second 440 Hz sine wave, 16-bit mono PCM.

Usage: python scripts/make_test_media.py
Uses only Pillow, numpy and the standard library wave module.
"""

import io
import wave
from pathlib import Path

import numpy as np
from PIL import Image

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "evidence" / "media"
IMAGE_SIZE = 256
PASTE_BOX = (96, 96)  # top-left corner of the 64x64 manipulated region
PASTE_SIZE = 64
PASTE_JPEG_QUALITY = 60  # strong recompression for a clear ELA discontinuity
RIPPLE_AMPLITUDE = 8  # subtle modulation so JPEG quantization has signal
RIPPLE_WAVELENGTH = 24
TONE_SAMPLE_RATE = 44100
TONE_FREQUENCY_HZ = 440
TONE_AMPLITUDE = 20000  # ~61% full scale so the sine does not clip


def build_gradient() -> Image.Image:
    """Build a smooth 256x256 RGB gradient with a subtle ripple."""
    axis = np.linspace(0, 255, IMAGE_SIZE)
    xx, yy = np.meshgrid(axis, axis)
    ripple = RIPPLE_AMPLITUDE * np.sin(xx / RIPPLE_WAVELENGTH * 2 * np.pi) * np.sin(
        yy / RIPPLE_WAVELENGTH * 2 * np.pi
    )
    red = np.clip(xx + ripple, 0, 255).astype(np.uint8)
    green = np.clip(yy + ripple, 0, 255).astype(np.uint8)
    blue = np.clip((xx + yy) / 2 + ripple, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([red, green, blue]), "RGB")


def build_manipulated(gradient: Image.Image) -> Image.Image:
    """Paste a separately JPEG-compressed 64x64 copy into the gradient."""
    region = gradient.crop(
        (PASTE_BOX[0], PASTE_BOX[1], PASTE_BOX[0] + PASTE_SIZE, PASTE_BOX[1] + PASTE_SIZE)
    )
    buffer = io.BytesIO()
    region.save(buffer, "JPEG", quality=PASTE_JPEG_QUALITY)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    manipulated = gradient.copy()
    manipulated.paste(recompressed, PASTE_BOX)
    return manipulated


def write_tone(path: Path) -> None:
    """Write a 1 second 440 Hz 16-bit mono PCM sine wave."""
    time = np.linspace(0, 1, TONE_SAMPLE_RATE, endpoint=False)
    samples = (np.sin(2 * np.pi * TONE_FREQUENCY_HZ * time) * TONE_AMPLITUDE).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(TONE_SAMPLE_RATE)
        wav_file.writeframes(samples.tobytes())


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    gradient = build_gradient()
    gradient.save(OUTPUT_DIR / "benign.png")
    build_manipulated(gradient).save(OUTPUT_DIR / "manipulated.png")
    write_tone(OUTPUT_DIR / "tone.wav")

    print(f"Test media written to {OUTPUT_DIR}:")
    for name in ("benign.png", "manipulated.png", "tone.wav"):
        print(f"  - {OUTPUT_DIR / name}")


if __name__ == "__main__":
    main()
