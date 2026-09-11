"""Train audio anti-spoofing model v1 (LCNN-style over log-Mel crops).

Data: ml/data/audio/manifest.csv produced by ml/fetch_audio_data.py
(ASVspoof 2019 LA train -> training, LA dev -> early-stopping/validation,
optional piper/wavefake/espeak fake subclasses). The real-world gate split
(datasets/media/real_world_audio/{fake,real}) is NEVER trained on — it is
evaluated after training and reported honestly in the metrics JSON.

Features: ml/audio_features.py — 80-bin log-Mel 3s crops (50% overlap) +
6 handcrafted statistics, cached as .pt shards under ml/cache/audio_v1/
using the same collision-free per-subclass sharding scheme as the image
cache (a shard is rebuilt whenever its path list no longer matches).

Training: class-weighted BCEWithLogitsLoss, Adam, early stopping patience 3
on dev F1 (fake class), CUDA AMP when a GPU is present.

Artifacts:
    ml/models/audio_cnn_v1.pt        state_dict + handcrafted-feature scaler
    ml/models/audio_v1_metrics.json  dev metrics + real-world gate metrics

Usage (from the backend directory):
    uv run python -m ml.train_audio_v1 --quick      # ~20k crops, 3 epochs
    uv run python -m ml.train_audio_v1 [--epochs 10] [--batch-size 128]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/ on sys.path for every launch style

import argparse
import csv
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from ml.audio_features import (
    decode_audio_16k,
    extract_crop_features,
    make_crops,
)
from ml.audio_model import AudioLCNNV1

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data" / "audio"
MANIFEST = DATA_DIR / "manifest.csv"
MODELS_DIR = ML_DIR / "models"
CACHE_DIR = ML_DIR / "cache" / "audio_v1"
REPO_ROOT = ML_DIR.parents[1]
REAL_WORLD_FAKE = REPO_ROOT / "datasets" / "media" / "real_world_audio" / "fake"
REAL_WORLD_REAL = REPO_ROOT / "datasets" / "media" / "real_world_audio" / "real"
REAL_SPEECH_SAMPLE = REPO_ROOT / "evidence" / "media" / "real_speech.wav"
SEED = 42
CACHE_SHARD_SIZE = 64  # utterances per shard
MAX_CROPS_PER_UTTERANCE_QUICK = 2


# ---------------------------------------------------------------------------
# Manifest + crop cache (per-subclass .pt shards, collision-free)
# ---------------------------------------------------------------------------

def load_manifest() -> list[dict]:
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        rows = [
            {
                "filepath": str(ML_DIR.parent / row["filepath"]),
                "label": int(row["label"]),
                "subclass": row["subclass"],
                "partition": row["partition"],
            }
            for row in csv.DictReader(fh)
            if row.get("filepath")
        ]
    if not rows:
        raise SystemExit("manifest is empty — run ml/fetch_audio_data.py first")
    return rows


def _utterance_features(path: str, max_crops: int | None) -> tuple[np.ndarray, np.ndarray]:
    """Decode -> crops -> (logmel float16 [N,80,T], handcraft float32 [N,6])."""
    with open(path, "rb") as fh:
        signal = decode_audio_16k(fh.read(), Path(path).name)
    crops = make_crops(signal, max_crops=max_crops)
    mels, hands = [], []
    for crop in crops:
        mel, hand = extract_crop_features(crop)
        mels.append(mel)
        hands.append(hand)
    return np.stack(mels).astype(np.float16), np.stack(hands).astype(np.float32)


def build_or_load_cache(rows: list[dict], max_crops: int | None) -> dict[str, dict]:
    """Cache crop features per subclass as .pt shards (image-cache scheme).

    Returns {"features": {subclass: (logmel [N,80,T] f16, handcraft [N,6] f32)},
             "counts": {subclass: [crops_per_utterance]},
             "positions": {subclass: {filepath: index}}}.
    """
    cache_dir = CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    by_subclass: dict[str, list[dict]] = {}
    for row in rows:
        by_subclass.setdefault(row["subclass"], []).append(row)

    features: dict[str, tuple] = {}
    positions: dict[str, dict[str, int]] = {}
    counts_table: dict[str, list[int]] = {}
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
                    if torch.load(shard, weights_only=False).get("paths") != expected_paths[start : start + CACHE_SHARD_SIZE]:
                        return False
                return True
            except Exception:
                return False

        if not shard_paths_valid():
            print(f"  caching {len(subset)} utterances for {subclass} ...", flush=True)
            from concurrent.futures import ThreadPoolExecutor

            started = time.time()
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda r: _utterance_features(r["filepath"], max_crops), subset))
            mels = np.concatenate([r[0] for r in results], axis=0)
            hands = np.concatenate([r[1] for r in results], axis=0)
            counts = [len(r[0]) for r in results]
            for shard_index, shard in enumerate(shards):
                start = sum(counts[: shard_index * CACHE_SHARD_SIZE])
                stop = sum(counts[: min((shard_index + 1) * CACHE_SHARD_SIZE, len(counts))])
                paths = expected_paths[shard_index * CACHE_SHARD_SIZE : (shard_index + 1) * CACHE_SHARD_SIZE]
                torch.save(
                    {
                        "paths": paths,
                        "counts": counts[shard_index * CACHE_SHARD_SIZE : (shard_index + 1) * CACHE_SHARD_SIZE],
                        "logmel": torch.from_numpy(mels[start:stop]),
                        "handcraft": torch.from_numpy(hands[start:stop]),
                    },
                    shard,
                )
            print(f"    cached {stop} crops in {time.time() - started:.0f}s")

        mels, hands, counts = [], [], []
        for shard in shards:
            stored = torch.load(shard, weights_only=False)
            mels.append(stored["logmel"])
            hands.append(stored["handcraft"])
            counts.extend(stored["counts"])
        features[subclass] = (torch.cat(mels), torch.cat(hands))
        counts_table[subclass] = counts
    return {"features": features, "counts": counts_table, "positions": positions}


def _specaugment(mel: torch.Tensor) -> torch.Tensor:
    """Light SpecAugment: 1 frequency + 1 time mask per crop (small width)."""
    _, freq, time = mel.shape
    if torch.rand(1).item() < 0.5 and freq > 8:
        width = int(torch.randint(2, 9, (1,)).item())
        start = int(torch.randint(0, freq - width, (1,)).item())
        mel[:, start : start + width, :] = mel.min()
    if torch.rand(1).item() < 0.5 and time > 20:
        width = int(torch.randint(5, 21, (1,)).item())
        start = int(torch.randint(0, time - width, (1,)).item())
        mel[:, :, start : start + width] = mel.min()
    return mel


class AudioCropDataset(Dataset):
    """Cached per-utterance crop features flattened into one crop per item.

    Returns (logmel [1,80,T] float32, handcraft [6] float32 standardised,
    label int); the default collate stacks tensors and labels.
    """

    def __init__(
        self,
        rows: list[dict],
        tables: dict[str, dict],
        mean: np.ndarray | None = None,
        std: np.ndarray | None = None,
        train: bool = False,
    ):
        self.train = train
        self.tables = tables
        self.mean = mean
        self.std = std
        self._crops: list[tuple[str, int, int]] = []  # (subclass, crop_index, label)
        for row in rows:
            subclass = row["subclass"]
            utterance = tables["positions"][subclass][row["filepath"]]
            counts = tables["counts"][subclass]
            start = int(sum(counts[:utterance]))
            for crop_index in range(start, start + int(counts[utterance])):
                self._crops.append((subclass, crop_index, row["label"]))

    def __len__(self) -> int:
        return len(self._crops)

    def __getitem__(self, idx: int) -> tuple:
        subclass, crop_index, label = self._crops[idx]
        mel = self.tables["features"][subclass][0][crop_index].float().unsqueeze(0)  # [1,80,T]
        hand = self.tables["features"][subclass][1][crop_index].float()
        if self.train:
            mel = _specaugment(mel)
        if self.mean is not None and self.std is not None:
            hand = (hand - self.mean) / self.std
        return mel, hand, label


def make_loader(dataset: AudioCropDataset, batch_size: int, train: bool) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=train,
        num_workers=0,  # features are in-memory tensors — workers add cost
        pin_memory=True,
    )


# ---------------------------------------------------------------------------
# Inference helper (shared by gate evaluation)
# ---------------------------------------------------------------------------

@torch.no_grad()
def predict_file(model, path: str, device, handcraft_mean, handcraft_std, max_crops: int | None = None) -> tuple[float, float, int]:
    """Per-file crop probabilities -> (mean_prob, max_prob, n_crops)."""
    with open(path, "rb") as fh:
        signal = decode_audio_16k(fh.read(), Path(path).name)
    crops = make_crops(signal, max_crops=max_crops)
    if not crops:
        return 0.5, 0.5, 0
    probs: list[float] = []
    for crop in crops:
        mel, hand = extract_crop_features(crop)
        mel_t = torch.from_numpy(mel.astype(np.float32)).unsqueeze(0).unsqueeze(0).to(device)
        hand_t = torch.from_numpy((hand - handcraft_mean) / handcraft_std).float().unsqueeze(0).to(device)
        with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
            logit = model(mel_t, hand_t)
        probs.append(float(torch.sigmoid(logit).item()))
    return float(np.mean(probs)), float(np.max(probs)), len(probs)


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="~20k crops, 3 epochs, CPU <20 min target")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--augment-piper", action="store_true", help="pass --augment-piper through to the fetcher first")
    parser.add_argument("--max-crops-per-utterance", type=int, default=None)
    args = parser.parse_args()

    if args.augment_piper:
        import subprocess
        import sys

        subprocess.run([sys.executable, str(ML_DIR / "fetch_audio_data.py"), "--augment-piper"], check=False)

    max_crops = args.max_crops_per_utterance or (MAX_CROPS_PER_UTTERANCE_QUICK if args.quick else None)
    epochs = args.epochs or (3 if args.quick else 10)

    torch.manual_seed(SEED)
    random.seed(SEED)
    np.random.seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  device={device} epochs={epochs} batch={args.batch_size} max_crops={max_crops}")

    rows = load_manifest()
    tables = build_or_load_cache(rows, max_crops)
    train_rows = [r for r in rows if r["partition"] == "train"]
    dev_rows = [r for r in rows if r["partition"] == "dev"]
    counts = Counter((r["subclass"], r["label"]) for r in train_rows)
    print(f"  train rows: {len(train_rows)} across {len(counts)} (subclass,label) pairs; dev rows: {len(dev_rows)}")

    # Standardisation statistics over TRAIN crops only.
    train_subclasses = sorted({r["subclass"] for r in train_rows})
    train_mels = np.concatenate([tables["features"][s][0].numpy() for s in train_subclasses], axis=0)
    train_hands = np.concatenate([tables["features"][s][1].numpy() for s in train_subclasses], axis=0)
    handcraft_mean = train_hands.mean(axis=0).astype(np.float32)
    handcraft_std = np.clip(train_hands.std(axis=0), 1e-6, None).astype(np.float32)
    mel_floor = float(train_mels.min())
    print(f"  train crops: {len(train_mels)}; logmel floor {mel_floor:.1f} dB")

    train_ds = AudioCropDataset(train_rows, tables, handcraft_mean, handcraft_std, train=True)
    dev_ds = AudioCropDataset(dev_rows, tables, handcraft_mean, handcraft_std, train=False)
    print(f"  crops: train={len(train_ds)} dev={len(dev_ds)}")
    train_loader = make_loader(train_ds, args.batch_size, train=True)
    dev_loader = make_loader(dev_ds, args.batch_size, train=False)

    model = AudioLCNNV1().to(device)
    n_real = sum(1 for _, _, label in train_ds._crops if label == 0)
    n_fake = sum(1 for _, _, label in train_ds._crops if label == 1)
    pos_weight = torch.tensor([n_real / max(n_fake, 1)], dtype=torch.float32).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)  # class-weighted BCE
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    def binary_f1(labels: list[int], preds: list[int]) -> float:
        from sklearn.metrics import f1_score

        return float(f1_score(labels, preds, pos_label=1, zero_division=0))

    @torch.no_grad()
    def evaluate(loader: DataLoader) -> tuple[list[int], list[int], list[float]]:
        model.eval()
        labels, preds, scores = [], [], []
        for mels, hands, targets in loader:
            mels = mels.to(device, non_blocking=True)
            hands = hands.to(device, non_blocking=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                logits = model(mels, hands)
            probs = torch.sigmoid(logits.float())
            scores.extend(probs.cpu().tolist())
            preds.extend((probs.cpu() >= 0.5).long().tolist())
            labels.extend(targets.tolist())
        return labels, preds, scores

    started = time.time()
    best_dev_f1 = -1.0
    best_state = None
    patience_left = 3  # early stopping patience on dev F1
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        seen = 0
        for mels, hands, targets in train_loader:
            mels = mels.to(device, non_blocking=True)
            hands = hands.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True).float()
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss = criterion(model(mels, hands), targets)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss += loss.item() * len(targets)
            seen += len(targets)
        dev_labels, dev_preds, _ = evaluate(dev_loader)
        dev_f1 = binary_f1(dev_labels, dev_preds)
        dev_acc = float(np.mean(np.array(dev_labels) == np.array(dev_preds)))
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(running_loss / max(seen, 1), 4),
                "dev_f1": round(dev_f1, 4),
                "dev_accuracy": round(dev_acc, 4),
            }
        )
        print(
            f"  epoch {epoch}/{epochs}: loss={running_loss / max(seen, 1):.4f} "
            f"dev_f1={dev_f1:.4f} dev_acc={dev_acc:.4f} elapsed={time.time() - started:.0f}s"
        )
        if dev_f1 > best_dev_f1:
            best_dev_f1 = dev_f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience_left = 3
        else:
            patience_left -= 1
            if patience_left <= 0:
                print("  early stopping (patience 3 on dev F1)")
                break
    wall_clock = time.time() - started

    if best_state is not None:
        model.load_state_dict(best_state)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = MODELS_DIR / "audio_cnn_v1.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "handcraft_mean": handcraft_mean,
            "handcraft_std": handcraft_std,
            "feature_params": {
                "sample_rate": 16000,
                "crop_seconds": 3,
                "n_mels": 80,
                "n_fft": 1024,
                "hop_length": 256,
                "norm_db": -60.0,
            },
        },
        artifact,
    )

    # --- dev metrics at the best checkpoint ---------------------------------
    dev_labels, dev_preds, dev_scores = evaluate(dev_loader)
    from sklearn.metrics import accuracy_score, roc_auc_score

    dev_metrics = {
        "f1": binary_f1(dev_labels, dev_preds),
        "accuracy": float(accuracy_score(dev_labels, dev_preds)),
        "auc": (
            float(roc_auc_score(dev_labels, dev_scores))
            if len(set(dev_labels)) > 1
            else None
        ),
    }

    # --- real-world gate (evaluation ONLY; reported honestly) ---------------
    model.eval()
    gate: dict[str, object] = {}
    elevenlabs = sorted(REAL_WORLD_FAKE.glob("*")) if REAL_WORLD_FAKE.exists() else []
    gate_files: list[dict] = []
    for clip in elevenlabs:
        mean_p, max_p, n_crops = predict_file(model, str(clip), device, handcraft_mean, handcraft_std)
        gate_files.append({"file": clip.name, "mean_prob": round(mean_p, 4), "max_prob": round(max_p, 4), "n_crops": n_crops})
    gate["elevenlabs_fake"] = {
        "n": len(gate_files),
        "recall_mean_prob>=0.5": round(float(np.mean([f["mean_prob"] >= 0.5 for f in gate_files])), 4) if gate_files else None,
        "recall_max_prob>=0.5": round(float(np.mean([f["max_prob"] >= 0.5 for f in gate_files])), 4) if gate_files else None,
        "per_file": gate_files,
    }
    real_files = [str(p) for p in (sorted(REAL_WORLD_REAL.glob("*")) if REAL_WORLD_REAL.exists() else [])]
    if REAL_SPEECH_SAMPLE.exists():
        real_files.append(str(REAL_SPEECH_SAMPLE))
    real_results: list[dict] = []
    for clip in real_files:
        mean_p, max_p, n_crops = predict_file(model, clip, device, handcraft_mean, handcraft_std)
        real_results.append({"file": Path(clip).name, "mean_prob": round(mean_p, 4), "max_prob": round(max_p, 4), "n_crops": n_crops})
    gate["real_speech"] = {
        "n": len(real_results),
        "fpr_mean_prob>=0.5": round(float(np.mean([f["mean_prob"] >= 0.5 for f in real_results])), 4) if real_results else None,
        "fpr_max_prob>=0.5": round(float(np.mean([f["max_prob"] >= 0.5 for f in real_results])), 4) if real_results else None,
        "per_file": real_results,
    }

    metrics = {
        "model": "AudioLCNNV1 (LCNN/MFM log-Mel CNN + 6-dim handcrafted branch)",
        "artifact": "audio_cnn_v1.pt",
        "epochs_run": len(history),
        "wall_clock_seconds": round(wall_clock, 1),
        "wall_clock_human": f"{int(wall_clock // 60)}m{int(wall_clock % 60):02d}s",
        "device": str(device),
        "quick": args.quick,
        "max_crops_per_utterance": max_crops,
        "train_rows": len(train_rows),
        "dev_rows": len(dev_rows),
        "train_crops": len(train_ds),
        "dev_crops": len(dev_ds),
        "class_counts_train": {"bonafide": n_real, "spoof": n_fake},
        "pos_weight": round(float(pos_weight.item()), 4),
        "best_dev_f1": best_dev_f1,
        "dev_metrics": dev_metrics,
        "history": history,
        "real_world_gate": gate,
        "real_world_gate_note": (
            "Gate split is NEVER trained on. ElevenLabs recall = fraction of "
            "user-contributed clips with probability >= 0.5; real-speech FPR = "
            "fraction of bona fide clips (user memos + one ASVspoof dev "
            "utterance) flagged >= 0.5. Modern codec TTS (ElevenLabs) is a "
            "DOMAIN SHIFT from ASVspoof 2019 vocoder attacks — read the recall "
            "as an honest transfer estimate, not an upper bound."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (MODELS_DIR / "audio_v1_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    # ----- report -------------------------------------------------------------
    print(f"\n  Training wall-clock: {metrics['wall_clock_human']} ({wall_clock:.0f}s) on {device}")
    print(f"  Dev metrics: f1={dev_metrics['f1']:.4f} acc={dev_metrics['accuracy']:.4f} auc={dev_metrics['auc']}")
    print("  Real-world gate (evaluation only):")
    print("  | Set | n | metric (>=0.5) |")
    print("  |---|---|---|")
    el = gate["elevenlabs_fake"]
    print(f"  | ElevenLabs fakes | {el['n']} | recall_mean={el['recall_mean_prob>=0.5']} recall_max={el['recall_max_prob>=0.5']} |")
    rs = gate["real_speech"]
    print(f"  | Real speech | {rs['n']} | fpr_mean={rs['fpr_mean_prob>=0.5']} fpr_max={rs['fpr_max_prob>=0.5']} |")
    for f in el["per_file"]:
        print(f"    fake  {f['file']}: mean={f['mean_prob']} max={f['max_prob']} crops={f['n_crops']}")
    for f in rs["per_file"]:
        print(f"    real  {f['file']}: mean={f['mean_prob']} max={f['max_prob']} crops={f['n_crops']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
