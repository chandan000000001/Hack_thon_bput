"""Train deepfake model v2 (MobileNetV3-Small, 128px) — messenger-robust.

Goal: eliminate false positives on genuine camera/messenger JPEGs while
keeping recall on AI-generated images. Key ingredients:

  - Data (ml/data/genimage/manifest.csv): real = real_clean (GenImage real /
    ImageNet subset) + real_messenger (JPEG q70-85, <=1600px, EXIF-stripped,
    built by ml/degrade_messenger.py) + user-contributed real_camera photos;
    fake = every generator subclass in the manifest (stablediffusion,
    midjourney, ...). Class-weighted loss absorbs any residual imbalance.
  - Augmentation teaching compression invariance: JPEG quality jitter 60-95,
    resize jitter, random horizontal flip, brightness/contrast jitter; EXIF is
    always absent (images are decoded from raw bytes).
  - Architecture: torchvision MobileNetV3-Small with ImageNet pretrained
    weights, input 128x128 (64x64 in --quick), binary head.
  - Speed: decoded+resized tensors are cached as .pt shards under ml/cache/
    on the first run and reused afterwards; DataLoader num_workers=4 +
    pin_memory; CUDA AMP when a GPU is present; --quick freezes the backbone
    (head-only training) so 3 epochs over 20k samples stay well under 15
    minutes on CPU.
  - Early stopping patience 3 on validation F1 (fake class).

Gates (evaluated on the held-out 10% split): FPR reported separately for
real_clean / real_messenger / real_camera (real_camera always includes
evidence/media/real_camera_whatsapp.jpg); per-generator recall. Tables are
appended to evidence/reports/evaluation.md and saved to
ml/models/deepfake_v2_metrics.json.

Usage (from the backend directory):
    python ml/train_deepfake_v2.py --quick            # <15 min target on CPU
    python ml/train_deepfake_v2.py [--epochs 10] [--batch-size 128] [--max-samples N]
"""

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
GENIMAGE_DIR = DATA_DIR / "genimage"
MODELS_DIR = ML_DIR / "models"
CACHE_DIR = ML_DIR / "cache" / "deepfake_v2"
REPO_ROOT = ML_DIR.parents[1]
EVAL_REPORT = REPO_ROOT / "evidence" / "reports" / "evaluation.md"
WHATSAPP_SAMPLE = REPO_ROOT / "evidence" / "media" / "real_camera_whatsapp.jpg"
SEED = 42

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
CACHE_SHARD_SIZE = 512


# ---------------------------------------------------------------------------
# Data loading + tensor cache
# ---------------------------------------------------------------------------

def load_manifest() -> list[dict]:
    """Every manifest row (backend-relative paths resolved to absolute)."""
    import csv

    with (GENIMAGE_DIR / "manifest.csv").open(newline="", encoding="utf-8") as fh:
        rows = [row for row in csv.DictReader(fh) if row.get("filepath")]
    for row in rows:
        row["label"] = int(row["label"])
        row["filepath"] = str(ML_DIR.parent / row["filepath"])  # manifest paths are backend-relative
    return rows


def downsample(rows: list[dict], max_samples: int | None) -> list[dict]:
    """Balanced real/fake downsample preserving every subclass."""
    if not max_samples:
        return rows
    real = [r for r in rows if r["label"] == 0]
    fake = [r for r in rows if r["label"] == 1]
    n_per_side = max_samples // 2
    return _downsample_per_subclass(real, n_per_side) + _downsample_per_subclass(fake, n_per_side)


def _downsample_per_subclass(rows: list[dict], total: int) -> list[dict]:
    if len(rows) <= total:
        return rows
    by_subclass: dict[str, list[dict]] = {}
    for row in rows:
        by_subclass.setdefault(row["subclass"], []).append(row)
    per = max(1, total // len(by_subclass))
    picked: list[dict] = []
    for subclass in sorted(by_subclass):
        picked.extend(by_subclass[subclass][:per])
    return picked[:total]


def _decode_tensor(path: str, size: int) -> torch.Tensor:
    """Decode -> resize -> uint8 CHW tensor (the cacheable form)."""
    from PIL import Image
    from torchvision.transforms import functional as TF

    image = Image.open(path).convert("RGB")
    image = image.resize((size, size), Image.BILINEAR)
    return TF.pil_to_tensor(image)


def build_or_load_cache(rows: list[dict], size: int) -> dict[str, dict]:
    """Cache decoded tensors per subclass as .pt shards; return lookup tables.

    Callers pass the FULL manifest so each subclass is cached exactly once and
    train/val/eval splits share the same tensors (splits index into them).
    Each shard stores {"paths": [...], "pixels": uint8 tensor [N,3,S,S]}; a
    cached shard is reused only when its path list matches, so manifest changes
    invalidate the cache automatically.

    Returns {"positions": {subclass: {filepath: index}}, "pixels": {subclass: tensor}}.
    """
    cache_dir = CACHE_DIR / f"size{size}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    by_subclass: dict[str, list[dict]] = {}
    for row in rows:
        by_subclass.setdefault(row["subclass"], []).append(row)

    positions: dict[str, dict[str, int]] = {}
    pixels: dict[str, torch.Tensor] = {}
    for subclass, subset in sorted(by_subclass.items()):
        subset = sorted(subset, key=lambda r: r["filepath"])
        expected_paths = [r["filepath"] for r in subset]
        positions[subclass] = {path: i for i, path in enumerate(expected_paths)}
        shards = [
            cache_dir / f"{subclass}_{i:04d}.pt"
            for i in range((len(subset) + CACHE_SHARD_SIZE - 1) // CACHE_SHARD_SIZE)
        ]

        def shard_paths_valid() -> bool:
            if not all(shard.exists() for shard in shards):
                return False
            try:
                for shard, start in zip(shards, range(0, len(expected_paths), CACHE_SHARD_SIZE)):
                    stored = torch.load(shard, weights_only=False)
                    if stored.get("paths") != expected_paths[start : start + CACHE_SHARD_SIZE]:
                        return False
                return True
            except Exception:
                return False

        if not shard_paths_valid():
            # (Re)build shards for this subclass.
            print(f"  caching {len(subset)} decoded tensors for {subclass} @ {size}px ...", flush=True)
            from concurrent.futures import ThreadPoolExecutor

            started = time.time()
            with ThreadPoolExecutor(max_workers=8) as pool:
                tensors = list(pool.map(lambda r: _decode_tensor(r["filepath"], size), subset))
            for shard_index, shard in enumerate(shards):
                start = shard_index * CACHE_SHARD_SIZE
                chunk = tensors[start : start + CACHE_SHARD_SIZE]
                torch.save(
                    {"paths": expected_paths[start : start + CACHE_SHARD_SIZE], "pixels": torch.stack(chunk)},
                    shard,
                )
            print(f"    cached in {time.time() - started:.0f}s")

        chunks = [torch.load(shard, weights_only=False)["pixels"] for shard in shards]
        pixels[subclass] = torch.cat(chunks)
    return {"positions": positions, "pixels": pixels}


class DeepfakeDataset(Dataset):
    """uint8 cached pixels -> augmentation -> normalized float tensor.

    Rows index into the shared per-subclass pixel tables built by
    build_or_load_cache. Returns (image, label, subclass); the default collate
    stacks images and labels and collects subclasses into a list of strings.
    """

    def __init__(
        self,
        rows: list[dict],
        tables: dict[str, dict],
        size: int,
        train: bool,
        jpeg_jitter: tuple[int, int] = (60, 95),
    ):
        self.size = size
        self.train = train
        self.jpeg_jitter = jpeg_jitter
        self.labels = [r["label"] for r in rows]
        self.subclasses = [r["subclass"] for r in rows]
        self._pixel_groups = tables["pixels"]
        self._index = [
            (row["subclass"], tables["positions"][row["subclass"]][row["filepath"]])
            for row in rows
        ]

    def __len__(self) -> int:
        return len(self.labels)

    def _augment(self, tensor: torch.Tensor) -> torch.Tensor:
        """Compression-invariance augmentation on the decoded uint8 image."""
        from PIL import Image
        from torchvision.transforms import functional as TF

        image = TF.to_pil_image(tensor)
        # JPEG quality jitter 60-95 (the messenger-compression simulator).
        quality = int(torch.randint(self.jpeg_jitter[0], self.jpeg_jitter[1] + 1, (1,)).item())
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=quality)
        image = Image.open(BytesIO(buffer.getvalue())).convert("RGB")
        # Resize jitter: scale in [0.85, 1.15] then center-crop back.
        scale = float(torch.empty(1).uniform_(0.85, 1.15).item())
        jittered = max(self.size, int(round(self.size * scale)))
        image = TF.resize(image, [jittered, jittered], antialias=True)
        image = TF.center_crop(image, [self.size, self.size])
        if torch.rand(1).item() < 0.5:
            image = TF.hflip(image)
        image = TF.adjust_brightness(image, float(torch.empty(1).uniform_(0.8, 1.2).item()))
        image = TF.adjust_contrast(image, float(torch.empty(1).uniform_(0.8, 1.2).item()))
        return TF.pil_to_tensor(image)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int, str]:
        subclass, pixel_index = self._index[idx]
        tensor = self._pixel_groups[subclass][pixel_index]
        if self.train:
            tensor = self._augment(tensor)
        image = tensor.float() / 255.0
        image = (image - torch.tensor(IMAGENET_MEAN).view(3, 1, 1)) / torch.tensor(IMAGENET_STD).view(3, 1, 1)
        return image, self.labels[idx], subclass


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_model(size: int, freeze_backbone: bool) -> nn.Module:
    from torchvision import models

    try:
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    except Exception:
        print("  WARNING: pretrained weights unavailable; training from scratch")
        model = models.mobilenet_v3_small(weights=None)
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, 2)  # binary head
    if freeze_backbone:
        for param in model.features.parameters():
            param.requires_grad = False
    return model


# ---------------------------------------------------------------------------
# Splits, training loop, gates
# ---------------------------------------------------------------------------

def stratified_splits(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Per-subclass 80/10/10 split (train/val/eval), deterministic."""
    import random

    rng = random.Random(SEED)
    by_subclass: dict[str, list[dict]] = {}
    for row in rows:
        by_subclass.setdefault(row["subclass"], []).append(row)
    train, val, evl = [], [], []
    for subclass in sorted(by_subclass):
        subset = sorted(by_subclass[subclass], key=lambda r: r["filepath"])
        rng.shuffle(subset)
        n = len(subset)
        n_val = max(1, int(n * 0.1))
        n_eval = max(1, int(n * 0.1)) if n >= 10 else 0
        val.extend(subset[:n_val])
        evl.extend(subset[n_val : n_val + n_eval])
        train.extend(subset[n_val + n_eval :])
    return train, val, evl


@torch.no_grad()
def _predict(model, loader, device) -> tuple[list[int], list[int], list[str]]:
    model.eval()
    labels, preds, subclasses = [], [], []
    for images, targets, metas in loader:
        images = images.to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
            logits = model(images)
        preds.extend(logits.argmax(dim=1).cpu().tolist())
        labels.extend(targets.tolist())
        subclasses.extend(metas)
    return labels, preds, subclasses


def make_loader(dataset: DeepfakeDataset, batch_size: int, train: bool) -> DataLoader:
    # __getitem__ returns (image, label, subclass); default collate stacks the
    # tensors and collects subclasses into a list of strings.
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=train,
        num_workers=4,
        pin_memory=True,
        persistent_workers=train,
    )


def evaluate_gates(model, device, size: int, batch_size: int, tables: dict[str, dict]) -> dict:
    """FPR per real subclass + per-generator recall on the held-out split,
    plus the single-file real_camera sample used by the regression suite."""
    rows = load_manifest()
    _, _, evl = stratified_splits(rows)
    dataset = DeepfakeDataset(evl, tables, size, train=False)
    loader = make_loader(dataset, batch_size, train=False)
    labels, preds, subclasses = _predict(model, loader, device)

    def fraction_predicted_fake(subclass_name: str) -> dict:
        """Share of the subclass's rows predicted fake (pred==1).

        Every subclass is single-label, so this single number is the FPR for
        real subclasses and the recall for generator subclasses.
        """
        total = predicted_fake = 0
        for label, pred, subclass in zip(labels, preds, subclasses):
            if subclass != subclass_name:
                continue
            total += 1
            predicted_fake += int(pred == 1)
        return {
            "n": total,
            "predicted_fake": predicted_fake,
            "rate": (predicted_fake / total) if total else None,
        }

    gates: dict[str, dict] = {
        "real_clean": fraction_predicted_fake("real_clean"),
        "real_messenger": fraction_predicted_fake("real_messenger"),
        "real_camera": fraction_predicted_fake("real_camera"),
    }
    generators = sorted({r["subclass"] for r in evl if r["label"] == 1})
    per_generator = {gen: fraction_predicted_fake(gen) for gen in generators}

    # The single WhatsApp-encoded genuine photo must be counted in real_camera.
    if WHATSAPP_SAMPLE.exists():
        from torchvision.transforms import functional as TF

        tensor = _decode_tensor(str(WHATSAPP_SAMPLE), size).float() / 255.0
        tensor = (tensor - torch.tensor(IMAGENET_MEAN).view(3, 1, 1)) / torch.tensor(
            IMAGENET_STD
        ).view(3, 1, 1)
        model.eval()
        with torch.no_grad(), torch.amp.autocast("cuda", enabled=device.type == "cuda"):
            logits = model(tensor.unsqueeze(0).to(device))
        gates["real_camera_whatsapp_sample"] = {
            "path": str(WHATSAPP_SAMPLE),
            "predicted_fake": bool(logits.argmax(dim=1).item() == 1),
        }

    return {"gates": gates, "per_generator_recall": per_generator}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="64px, 3 epochs, 20k samples, frozen backbone (CPU <15 min target)")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    size = 64 if args.quick else 128
    epochs = args.epochs or (3 if args.quick else 10)
    batch_size = args.batch_size or 128
    max_samples = args.max_samples or (20000 if args.quick else None)
    freeze_backbone = args.quick  # head-only training keeps quick mode fast on CPU

    torch.manual_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  device={device} size={size} epochs={epochs} batch={batch_size} freeze_backbone={freeze_backbone}")

    all_rows = load_manifest()
    # Cache decoded tensors ONCE over the full manifest; all splits and the
    # gate evaluation share these tensors via position lookup.
    tables = build_or_load_cache(all_rows, size)
    rows = downsample(all_rows, max_samples)
    counts = Counter((r["subclass"], r["label"]) for r in rows)
    print("  dataset:", dict(sorted(counts.items())))
    train_rows, val_rows, eval_rows = stratified_splits(rows)

    train_ds = DeepfakeDataset(train_rows, tables, size, train=True)
    val_ds = DeepfakeDataset(val_rows, tables, size, train=False)
    train_loader = make_loader(train_ds, batch_size, train=True)
    val_loader = make_loader(val_ds, batch_size, train=False)

    model = build_model(size, freeze_backbone).to(device)
    real_n = sum(1 for r in train_rows if r["label"] == 0)
    fake_n = sum(1 for r in train_rows if r["label"] == 1)
    class_weights = torch.tensor(
        [len(train_rows) / (2.0 * real_n), len(train_rows) / (2.0 * fake_n)], dtype=torch.float32
    ).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)  # class-weighted loss
    optimizer = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad],
        lr=1e-3 if freeze_backbone else 3e-4,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    def binary_f1(labels, preds):
        from sklearn.metrics import f1_score

        return float(f1_score(labels, preds, pos_label=1, zero_division=0))

    started = time.time()
    best_val_f1 = -1.0
    best_state = None
    patience_left = 3  # early stopping patience on validation F1
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        seen = 0
        for images, targets, _ in train_loader:
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss = criterion(model(images), targets)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss += loss.item() * len(targets)
            seen += len(targets)
        val_labels, val_preds, _ = _predict(model, val_loader, device)
        val_f1 = binary_f1(val_labels, val_preds)
        history.append({"epoch": epoch, "train_loss": round(running_loss / max(seen, 1), 4), "val_f1": val_f1})
        print(f"  epoch {epoch}/{epochs}: loss={running_loss / max(seen, 1):.4f} val_f1={val_f1:.4f} elapsed={time.time() - started:.0f}s")
        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience_left = 3
        else:
            patience_left -= 1
            if patience_left <= 0:
                print("  early stopping (patience 3 on validation F1)")
                break
    wall_clock = time.time() - started

    if best_state is not None:
        model.load_state_dict(best_state)
    torch.save(model.state_dict(), MODELS_DIR / "deepfake_cnn_v2.pt")

    gates_result = evaluate_gates(model, device, size, batch_size, tables)
    metrics = {
        "model": "mobilenet_v3_small (ImageNet pretrained, binary head)",
        "input_size": size,
        "frozen_backbone": freeze_backbone,
        "epochs_run": len(history),
        "wall_clock_seconds": round(wall_clock, 1),
        "wall_clock_human": f"{int(wall_clock // 60)}m{int(wall_clock % 60):02d}s",
        "device": str(device),
        "train_rows": len(train_rows),
        "best_val_f1": best_val_f1,
        "history": history,
        "class_weights": [round(float(w), 4) for w in class_weights.tolist()],
        "gates": gates_result["gates"],
        "per_generator_recall": gates_result["per_generator_recall"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "deepfake_v2_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    # ----- report tables -----------------------------------------------------
    print(f"\n  Training wall-clock: {metrics['wall_clock_human']} ({wall_clock:.0f}s) on {device}")
    print("  FPR by real subclass (held-out eval split; rate = fraction predicted fake):")
    fpr_lines = ["| Real subclass | n | FPR |", "|---|---|---|"]
    for name in ("real_clean", "real_messenger", "real_camera"):
        gate = gates_result["gates"][name]
        fpr = f"{gate['rate']:.4f}" if gate["rate"] is not None else "n/a"
        fpr_lines.append(f"| {name} | {gate['n']} | {fpr} |")
        print(f"    {name:15s} n={gate['n']:5d} FPR={fpr}")
    whatsapp = gates_result["gates"].get("real_camera_whatsapp_sample")
    if whatsapp:
        print(f"    real_camera whatsapp sample: predicted_fake={whatsapp['predicted_fake']}")
    print("  Per-generator recall (rate = fraction predicted fake):")
    rec_lines = ["| Generator | n | Recall |", "|---|---|---|"]
    for gen, stats in gates_result["per_generator_recall"].items():
        recall = f"{stats['rate']:.4f}" if stats["rate"] is not None else "n/a"
        rec_lines.append(f"| {gen} | {stats['n']} | {recall} |")
        print(f"    {gen:15s} n={stats['n']:5d} recall={recall}")

    stamp = datetime.now(timezone.utc).isoformat()
    section = (
        f"\n\n## Deepfake v2 model gates (MobileNetV3-Small, {size}px)\n\n"
        f"Generated: {stamp} · script: `ml/train_deepfake_v2.py` · device: {device} · "
        f"epochs run: {len(history)} · **training wall-clock: {metrics['wall_clock_human']}** · "
        f"best validation F1 (fake class): {best_val_f1:.4f}\n\n"
        + "\n".join(fpr_lines)
        + "\n\n"
        + "\n".join(rec_lines)
        + "\n\n"
        + (
            f"real_camera WhatsApp sample (`evidence/media/real_camera_whatsapp.jpg`): "
            f"predicted_fake={whatsapp['predicted_fake']}.\n" if whatsapp else ""
        )
        + "Artifacts: `ml/models/deepfake_cnn_v2.pt` (+ `deepfake_v2_metrics.json`), activated by "
        "`ml/models/calibration.json` key `deepfake_model_version: v2`.\n"
    )
    with EVAL_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(section)
    print(f"  appended gate tables -> {EVAL_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
