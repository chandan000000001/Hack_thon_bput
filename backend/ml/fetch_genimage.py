"""Fetch GenImage benchmark subsets for deepfake v2 training (real + generators).

Downloads per-generator arrow shards from the HF mirror `nebula/GenImage-arrow`
(each shard holds BOTH classes: the ImageNet-derived real subset and the
generator's fake images), writes them to ml/data/genimage/<subclass>/ and
records provenance in ml/data/genimage/provenance.json + manifest.csv.

Generators default to Stable Diffusion v1.4 and Midjourney (spec: at least
two). Per-class download is capped at 20000 images (--max-per-class). The
existing CIFAKE data (ml/data/images/) is kept untouched as an additional
fake/real source.

Fallback: when the download fails entirely (no network, rate limit, ...), the
manifest is built from the existing CIFAKE split instead so training can still
run; the fallback is recorded in provenance.json.

Usage (from the backend directory):
    python ml/fetch_genimage.py [--shards-per-generator 3] [--max-per-class 20000]
"""

import argparse
import csv
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
GENIMAGE_DIR = DATA_DIR / "genimage"
CIFAKE_TRAIN_DIR = DATA_DIR / "images" / "train"

HF_REPO = "nebula/GenImage-arrow"
HF_URL = "https://huggingface.co/datasets/nebula/GenImage-arrow"
HF_LICENSE = "CC BY-NC-SA 4.0"

# generator bundle dir -> subclass name used by training/evaluation
GENERATORS = {
    "stable_diffusion_v_1_4": "stablediffusion",
    "Midjourney": "midjourney",
}


def _save_image(raw: bytes, source_name: str, out_dir: Path) -> Path:
    """Write one image keyed by content hash (dedupes across bundles)."""
    digest = hashlib.md5(raw).hexdigest()
    suffix = Path(source_name).suffix.lower() or ".jpg"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{digest}{suffix}"
    if not out_path.exists():
        out_path.write_bytes(raw)
    return out_path


def _existing_manifest_rows() -> list[dict]:
    manifest = GENIMAGE_DIR / "manifest.csv"
    if not manifest.exists():
        return []
    with manifest.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fetch_from_hf(max_per_class: int, shards_per_generator: int) -> tuple[list[dict], list[dict]]:
    """Download shards per generator and return (manifest_rows, provenance_entries).

    Per-generator failures are tolerated (the bundle is marked 'failed' and
    fetching continues); a full CIFAKE fallback only happens when no generator
    yielded any images at all.
    """
    from datasets import Dataset
    from huggingface_hub import HfApi, hf_hub_download

    manifest_rows: list[dict] = _existing_manifest_rows()
    have = {row["filepath"] for row in manifest_rows}
    counts: dict[str, int] = {"real_clean": sum(1 for r in manifest_rows if r["subclass"] == "real_clean")}
    for gen_dir in GENERATORS.values():
        counts.setdefault(gen_dir, sum(1 for r in manifest_rows if r["subclass"] == gen_dir))

    api = HfApi()
    all_files = api.list_repo_files(HF_REPO, repo_type="dataset")
    provenance: list[dict] = []
    for bundle, subclass in GENERATORS.items():
        shard_files = sorted(
            f for f in all_files
            if f.startswith(f"data/train/{bundle}/data-") and f.endswith(".arrow")
        )[:shards_per_generator]
        fetched_fake = counts.get(subclass, 0)
        status, error_note = "fetched", None
        try:
            if not shard_files:
                raise RuntimeError(f"no arrow shards found under data/train/{bundle}/")
            for filename in shard_files:
                if counts["real_clean"] >= max_per_class and fetched_fake >= max_per_class:
                    break
                print(f"  downloading {filename} ...", flush=True)
                started = time.time()
                local_path = hf_hub_download(repo_id=HF_REPO, repo_type="dataset", filename=filename)
                print(f"    done in {time.time() - started:.0f}s", flush=True)

                ds = Dataset.from_file(local_path)
                for row in ds:
                    label = int(row["label"])  # 0 = real (ImageNet subset), 1 = fake
                    if label == 0:
                        if counts["real_clean"] >= max_per_class:
                            continue
                        out_dir = GENIMAGE_DIR / "real_clean"
                    else:
                        if fetched_fake >= max_per_class:
                            continue
                        out_dir = GENIMAGE_DIR / subclass
                    out_path = _save_image(row["image"], row["image_path"], out_dir)
                    rel = str(out_path.relative_to(ML_DIR.parent))
                    if rel not in have:
                        manifest_rows.append(
                            {
                                "filepath": rel,
                                "label": label,
                                "subclass": out_dir.name,
                                "source": f"genimage/{bundle}",
                                "width": row["width"],
                                "height": row["height"],
                            }
                        )
                        have.add(rel)
                    if label == 0:
                        counts["real_clean"] += 1
                    else:
                        fetched_fake += 1
                        counts[subclass] = fetched_fake
        except Exception as exc:
            status, error_note = "failed", str(exc)
            print(f"  generator {bundle} FAILED ({exc}); continuing with the others")

        provenance.append(
            {
                "source": f"genimage/{bundle}",
                "url": f"{HF_URL}/tree/main/data/train/{bundle}",
                "hf_repo": HF_REPO,
                "hf_filename_prefix": f"data/train/{bundle}/",
                "licence": HF_LICENSE,
                "status": status,
                "error": error_note,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "rows_written": counts.get(subclass, 0),
                "capped_at": max_per_class,
            }
        )
        print(f"  {subclass}: {counts.get(subclass, 0)} fake images (real_clean total {counts['real_clean']})")

    if all(counts.get(gen, 0) == 0 for gen in GENERATORS.values()):
        raise RuntimeError("no generator yielded any images")
    provenance.append(
        {
            "source": "genimage/real_imagenet",
            "url": f"{HF_URL} (real class bundled with every generator shard)",
            "hf_repo": HF_REPO,
            "licence": HF_LICENSE,
            "status": "fetched" if counts["real_clean"] else "failed",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "rows_written": counts["real_clean"],
            "capped_at": max_per_class,
        }
    )
    return manifest_rows, provenance


def build_cifake_fallback(max_per_class: int) -> tuple[list[dict], list[dict]]:
    """Build the manifest from the on-disk CIFAKE split when the download fails."""
    manifest_rows: list[dict] = []
    for subclass, class_dir, label in (
        ("real_clean", CIFAKE_TRAIN_DIR / "real", 0),
        ("cifake", CIFAKE_TRAIN_DIR / "fake", 1),
    ):
        written = 0
        for image_path in sorted(class_dir.glob("*.png")):
            if written >= max_per_class:
                break
            rel = image_path.relative_to(ML_DIR.parent)
            manifest_rows.append(
                {
                    "filepath": str(rel),
                    "label": label,
                    "subclass": subclass,
                    "source": "cifake",
                    "width": 32,
                    "height": 32,
                }
            )
            written += 1
        print(f"  fallback cifake/{subclass}: {written} images")
    provenance = [
        {
            "source": "cifake",
            "url": "https://huggingface.co/datasets/dragonintelligence/CIFAKE-image-dataset",
            "licence": "CIFAKE (research); on-disk copy under ml/data/images/",
            "status": "synthetic_fallback",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "note": "GenImage download failed; CIFAKE is the fallback source.",
        }
    ]
    return manifest_rows, provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-per-class", type=int, default=20000, help="download cap per class (spec: 20000)")
    parser.add_argument("--shards-per-generator", type=int, default=3, help="arrow shards fetched per generator bundle")
    args = parser.parse_args()

    GENIMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        manifest_rows, provenance = fetch_from_hf(args.max_per_class, args.shards_per_generator)
    except Exception as exc:
        print(f"  GenImage download FAILED ({exc}); falling back to CIFAKE")
        manifest_rows, provenance = build_cifake_fallback(args.max_per_class)

    with (GENIMAGE_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["filepath", "label", "subclass", "source", "width", "height"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {}
    for row in manifest_rows:
        summary[row["subclass"]] = summary.get(row["subclass"], 0) + 1
    provenance_doc = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_script": "ml/fetch_genimage.py",
        "summary": summary,
        "entries": provenance,
    }
    (GENIMAGE_DIR / "provenance.json").write_text(
        json.dumps(provenance_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("  manifest summary:", summary)
    print(f"  wrote manifest.csv + provenance.json -> {GENIMAGE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
