"""Build the real_messenger subclass and manage the real_camera contributor dir.

Messenger apps (WhatsApp, Telegram, ...) re-encode every photo they send:
downscale to a long-side cap, recompress at moderate JPEG quality and drop
EXIF. A deepfake model trained only on pristine photos misfires on exactly
those images, so this script derives a *real_messenger* subclass from the
real-class images (GenImage real / ImageNet subset, or CIFAKE real as
fallback):

  - resize longest side to <= 1600 (downscale only)
  - JPEG quality sampled uniformly from 70-85
  - EXIF always stripped (PIL re-save carries no metadata)
  - optional mild sharpening (--sharpen): UnsharpMask(radius=1, percent=60)

It also accepts user-contributed genuine camera photos in
datasets/media/real_camera/ (contributor guidance: use NON-SENSITIVE personal
images — see datasets/media/real_camera/README.txt). Those files are never
modified; they are referenced by the manifest as the *real_camera* evaluation
split.

Finally it writes evidence/media/real_camera_whatsapp.jpg — one genuine
photo in messenger encoding — used by the regression suite.

Usage (from the backend directory):
    python ml/degrade_messenger.py [--count 10000] [--sharpen]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/ on sys.path for every launch style

import argparse
import csv
import random
import shutil
from pathlib import Path

from PIL import Image

ML_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ML_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
GENIMAGE_DIR = ML_DIR / "data" / "genimage"
REAL_CAMERA_DIR = REPO_ROOT / "datasets" / "media" / "real_camera"
WHATSAPP_SAMPLE_PATH = REPO_ROOT / "evidence" / "media" / "real_camera_whatsapp.jpg"
SEED = 42

MESSENGER_LONG_SIDE = 1600
MESSENGER_QUALITY_RANGE = (70, 85)


def load_real_sources(max_needed: int) -> list[Path]:
    """Real-class images: GenImage real_clean first, CIFAKE real as fallback."""
    real_dir = GENIMAGE_DIR / "real_clean"
    if real_dir.exists() and any(real_dir.iterdir()):
        sources = sorted(real_dir.iterdir())
    else:
        cifake_real = ML_DIR / "data" / "images" / "train" / "real"
        sources = sorted(cifake_real.glob("*.png"))
    return sources[:max_needed]


def degrade(image: Image.Image, rng: random.Random, sharpen: bool) -> Image.Image:
    """Apply the messenger pipeline to a PIL image (EXIF never survives)."""
    longest = max(image.size)
    if longest > MESSENGER_LONG_SIDE:
        scale = MESSENGER_LONG_SIDE / longest
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.LANCZOS,
        )
    if sharpen:
        from PIL import ImageFilter

        image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    return image


def build_real_messenger(count: int, sharpen: bool) -> list[dict]:
    rng = random.Random(SEED)
    out_dir = GENIMAGE_DIR / "real_messenger"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("messenger_*.jpg"):
        stale.unlink()  # rebuild from scratch (a previous fallback run may have used CIFAKE sources)
    sources = load_real_sources(count)
    if not sources:
        raise SystemExit("No real-class source images found (run ml/fetch_genimage.py first)")

    rows: list[dict] = []
    for index in range(count):
        source = sources[index % len(sources)]
        image = Image.open(source).convert("RGB")
        image = degrade(image, rng, sharpen)
        quality = rng.randint(*MESSENGER_QUALITY_RANGE)
        out_path = out_dir / f"messenger_{index:05d}.jpg"
        image.save(out_path, "JPEG", quality=quality)  # no exif argument -> stripped
        rows.append(
            {
                "filepath": str(out_path.relative_to(BACKEND_DIR)),
                "label": 0,
                "subclass": "real_messenger",
                "source": "messenger_degradation",
                "width": image.width,
                "height": image.height,
            }
        )
        if (index + 1) % 1000 == 0:
            print(f"  real_messenger: {index + 1}/{count}")
    return rows


def write_whatsapp_sample(sharpen: bool) -> None:
    """Save one genuine photo in WhatsApp-style encoding for the regression."""
    rng = random.Random(SEED + 1)
    sources = load_real_sources(50)
    image = Image.open(sources[0]).convert("RGB")
    image = degrade(image, rng, sharpen)
    WHATSAPP_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(WHATSAPP_SAMPLE_PATH, "JPEG", quality=78)
    print(f"  wrote {WHATSAPP_SAMPLE_PATH} ({image.width}x{image.height}, q78, EXIF stripped)")


def collect_real_camera(existing_rows: list[dict]) -> list[dict]:
    """Reference user-contributed genuine photos as the real_camera split."""
    REAL_CAMERA_DIR.mkdir(parents=True, exist_ok=True)
    readme = REAL_CAMERA_DIR / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Contributed genuine camera photos for the real_camera evaluation split.\n\n"
            "Contributor guidance: use NON-SENSITIVE personal images only (no faces of\n"
            "private individuals you cannot share, no documents, no location-revealing\n"
            "metadata). Files here are referenced for evaluation and never modified.\n",
            encoding="utf-8",
        )
    rows: list[dict] = []
    for pattern in ("*.jpg", "*.jpeg", "*.png"):
        for path in sorted(REAL_CAMERA_DIR.glob(pattern)):
            if path.name == readme.name:
                continue
            image = Image.open(path)
            rows.append(
                {
                    "filepath": str(path.relative_to(BACKEND_DIR)),
                    "label": 0,
                    "subclass": "real_camera",
                    "source": "user_contributed",
                    "width": image.width,
                    "height": image.height,
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10000, help="real_messenger images to build (spec: 10000)")
    parser.add_argument("--sharpen", action="store_true", help="apply optional mild sharpening")
    args = parser.parse_args()

    print(f"  building {args.count} real_messenger images (q{MESSENGER_QUALITY_RANGE[0]}-{MESSENGER_QUALITY_RANGE[1]}, <= {MESSENGER_LONG_SIDE}px, EXIF stripped)")
    rows = build_real_messenger(args.count, args.sharpen)
    write_whatsapp_sample(args.sharpen)
    camera_rows = collect_real_camera(rows)
    print(f"  real_camera split: {len(camera_rows)} contributed images from {REAL_CAMERA_DIR}")

    # Append the new rows to the genimage manifest (idempotent by filepath).
    manifest = GENIMAGE_DIR / "manifest.csv"
    with manifest.open(newline="", encoding="utf-8") as fh:
        existing = list(csv.DictReader(fh))
    have = {row["filepath"] for row in existing}
    for row in rows + camera_rows:
        if row["filepath"] not in have:
            existing.append(row)
    fieldnames = ["filepath", "label", "subclass", "source", "width", "height"]
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)

    summary: dict[str, int] = {}
    for row in existing:
        summary[row["subclass"]] = summary.get(row["subclass"], 0) + 1
    print("  manifest summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
