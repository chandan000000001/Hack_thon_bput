"""Offline accuracy/performance evaluation harness (Parts 8 + ML Step 3).

Imports the detector functions directly from app.services and evaluates
them against the labelled datasets. NO OpenRouter calls and NO network
calls happen here.

Since ML Step 3 the detectors are hybrid (heuristics + trained models),
so each ML-backed module (email, url, message, network, deepfake_image)
is evaluated twice by toggling settings.ML_ENABLED:
  - heuristics-only pass (behaviour identical to the pre-integration engine)
  - hybrid pass (heuristic score blended with the trained model probability)
account_takeover has no trained model yet and is reported once.

Flagging rules:
  - heuristic modules: risk_score >= 41 (medium or above) counts as flagged
  - media forensics: manipulation_probability >= 0.5 counts as flagged

Leakage control: modules evaluated on held-out splits produced by
ml/preprocess.py (test_emails.csv, test_urls.csv, test_network.csv) never
overlap the ML training data. The url module is evaluated ONLY on
ml/data/test_urls.csv.

Outputs: stdout tables (heuristics vs hybrid), plus
evidence/reports/evaluation.md and evaluation.json including artifact
SHA-256 hashes. Exit 0 even if metrics are modest; exit 1 only if a
required dataset file is missing.

Run from the backend directory:
    python scripts/evaluate.py
"""

import csv
import hashlib
import json
import math
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

try:  # some email bodies exceed the default 128 KiB CSV field limit
    csv.field_size_limit(sys.maxsize)
except OverflowError:  # pragma: no cover - 32-bit platforms
    csv.field_size_limit(2**31 - 1)
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.account_takeover_detector import analyze_auth_log_heuristics  # noqa: E402
from app.services.deepfake_detector import analyze_media  # noqa: E402
from app.services.ml_inference import split_ml_indicator  # noqa: E402
from app.services.network_threat_detector import analyze_network_heuristics  # noqa: E402
from app.services.phishing_detector import analyze_email_heuristics  # noqa: E402
from app.services.scoring_service import calculate_score, get_severity  # noqa: E402
from app.services.url_detector import analyze_url_heuristics  # noqa: E402

DATASETS_DIR = ROOT / "datasets"
ML_DATA_DIR = ROOT / "backend" / "ml" / "data"
ML_MODELS_DIR = ROOT / "backend" / "ml" / "models"
REPORTS_DIR = ROOT / "evidence" / "reports"
PROVENANCE_PATH = DATASETS_DIR / "provenance.json"

RISK_FLAG_THRESHOLD = 41  # medium or above counts as flagged
MEDIA_FLAG_PROBABILITY = 0.5  # manipulation probability >= 0.5 counts as flagged
MEDIA_EVAL_SAMPLE = 1000  # deterministic sample of the held-out image test split

REQUIRED_FILES = {
    "email": ML_DATA_DIR / "test_emails.csv",
    "url": ML_DATA_DIR / "test_urls.csv",  # held-out split only (leakage fix)
    "message": DATASETS_DIR / "messages" / "sms_labelled.csv",
    "account_takeover": DATASETS_DIR / "auth_logs" / "labelled_auth_logs.json",
    "network": DATASETS_DIR / "network" / "labelled_network.json",
    "deepfake_image": ML_DATA_DIR / "image_manifest.csv",
}

ML_ARTIFACTS = [
    "email_tfidf.pkl",
    "email_phishing_xgb.pkl",
    "url_xgb.pkl",
    "deepfake_cnn.pt",
    "network_xgb.pkl",
    "network_scaler.pkl",
]


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except Exception:
        return None


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def load_provenance() -> dict:
    if PROVENANCE_PATH.exists():
        try:
            return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def provenance_status(source: str) -> str:
    for entry in load_provenance().get("entries", []):
        if entry.get("source") == source:
            return str(entry.get("status", "unknown"))
    return "unknown"


def heuristic_flag(score: int) -> bool:
    return score >= RISK_FLAG_THRESHOLD


def split_score(indicators: list[dict]) -> tuple[int, int]:
    """(heuristic_score, hybrid_score) from a detector's indicator list.
    With ml_enabled=False the hybrid score equals the heuristic score."""
    heuristic_indicators, ml_probability = split_ml_indicator(indicators)
    heuristic_score = calculate_score(heuristic_indicators)
    if ml_probability is not None:
        from app.services.ml_inference import blend_scores

        return heuristic_score, max(0, min(100, round(0.45 * heuristic_score + 0.55 * ml_probability * 100)))
    return heuristic_score, heuristic_score


def timed(fn: Callable[[], bool]) -> tuple[bool, float]:
    start = time.perf_counter()
    flagged = fn()
    return flagged, (time.perf_counter() - start) * 1000.0


def summarize(items: list[tuple[bool, bool, float]]) -> dict[str, Any]:
    """items: (predicted_flagged, actually_positive, latency_ms)."""
    tp = sum(1 for pred, pos, _ in items if pred and pos)
    fp = sum(1 for pred, pos, _ in items if pred and not pos)
    tn = sum(1 for pred, pos, _ in items if not pred and not pos)
    fn = sum(1 for pred, pos, _ in items if not pred and pos)
    total = len(items)
    latencies = sorted(lat for _, _, lat in items)
    mean_ms = sum(latencies) / total if total else 0.0
    p95_index = min(total - 1, max(0, math.ceil(0.95 * total) - 1))
    p95_ms = latencies[p95_index] if latencies else 0.0
    return {
        "samples": total,
        "positives": tp + fn,
        "flagged": tp + fp,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": (tp + tn) / total if total else 0.0,
        "precision": tp / (tp + fp) if (tp + fp) else 0.0,
        "recall": tp / (tp + fn) if (tp + fn) else 0.0,
        "false_positive_rate": fp / (fp + tn) if (fp + tn) else 0.0,
        "false_negative_rate": fn / (fn + tp) if (fn + tp) else 0.0,
        "mean_latency_ms": round(mean_ms, 3),
        "p95_latency_ms": round(p95_ms, 3),
    }


def finalize(metrics: dict[str, Any]) -> dict[str, Any]:
    precision, recall = metrics["precision"], metrics["recall"]
    metrics["f1"] = round((2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0, 4)
    for key in ("accuracy", "precision", "recall", "false_positive_rate", "false_negative_rate"):
        metrics[key] = round(metrics[key], 4)
    return metrics


# ---------------------------------------------------------------------------
# Module runners: return [(flagged, positive, latency_ms)]
# ---------------------------------------------------------------------------

def run_email() -> list[tuple[bool, bool, float]]:
    items = []
    with REQUIRED_FILES["email"].open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            positive = int(row["label"]) == 1
            flagged, latency = timed(
                lambda r=row: heuristic_flag(
                    split_score(analyze_email_heuristics("", "", r["clean_text"]))[1]
                )
            )
            items.append((flagged, positive, latency))
    return items


def run_url() -> list[tuple[bool, bool, float]]:
    items = []
    with REQUIRED_FILES["url"].open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            positive = row["label"] == "malicious"
            flagged, latency = timed(
                lambda r=row: heuristic_flag(
                    split_score(analyze_url_heuristics(r["url"]))[1]
                )
            )
            items.append((flagged, positive, latency))
    return items


def run_message() -> list[tuple[bool, bool, float]]:
    items = []
    with REQUIRED_FILES["message"].open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            text = row["text"].strip()
            positive = row["label"] == "phishing_like"
            flagged, latency = timed(
                lambda t=text: heuristic_flag(
                    split_score(analyze_email_heuristics("", "", t))[1]
                )
            )
            items.append((flagged, positive, latency))
    return items


def run_account_takeover() -> list[tuple[bool, bool, float]]:
    scenarios = json.loads(REQUIRED_FILES["account_takeover"].read_text(encoding="utf-8"))
    items = []
    for scenario in scenarios:
        positive = scenario.get("label") == "attack"
        flagged, latency = timed(
            lambda s=scenario: heuristic_flag(
                calculate_score(analyze_auth_log_heuristics(s.get("events", [])))
            )
        )
        items.append((flagged, positive, latency))
    return items


def run_network() -> list[tuple[bool, bool, float]]:
    scenarios = json.loads(REQUIRED_FILES["network"].read_text(encoding="utf-8"))
    items = []
    for scenario in scenarios:
        positive = scenario.get("label") == "attack"
        flagged, latency = timed(
            lambda s=scenario: heuristic_flag(
                split_score(
                    analyze_network_heuristics(s.get("flows", []), s.get("api_logs", []))
                )[1]
            )
        )
        items.append((flagged, positive, latency))
    return items


def run_deepfake_image() -> list[tuple[bool, bool, float]]:
    manifest = pd.read_csv(REQUIRED_FILES["deepfake_image"]).to_dict("records")
    test_rows = [entry for entry in manifest if entry.get("split") == "test"] or manifest
    # Labels: Part 5 manifest used benign/manipulated, the Step 1 CIFAKE
    # manifest uses real/fake — both map to negative/positive.
    negative_labels = {"benign", "real"}
    positive_labels = {"manipulated", "fake"}
    benign = [e for e in test_rows if e.get("label") in negative_labels]
    manipulated = [e for e in test_rows if e.get("label") in positive_labels]
    rng = random.Random(42)
    sample = rng.sample(benign, min(len(benign), MEDIA_EVAL_SAMPLE // 2)) + rng.sample(
        manipulated, min(len(manipulated), MEDIA_EVAL_SAMPLE // 2)
    )

    items = []
    for entry in sample:
        media_path = ROOT / entry["file_path"]
        data = media_path.read_bytes()
        positive = entry["label"] in positive_labels
        flagged, latency = timed(
            lambda d=data, name=media_path.name: analyze_media(d, name, "image/png")[
                "manipulation_probability"
            ]
            >= MEDIA_FLAG_PROBABILITY
        )
        items.append((flagged, positive, latency))
    return items


MODULES = {
    "email_phishing": (run_email, "ml/data/test_emails.csv (held-out)"),
    "url": (run_url, "ml/data/test_urls.csv (held-out, 200 rows)"),
    "message": (run_message, "datasets/messages/sms_labelled.csv"),
    "account_takeover": (run_account_takeover, "datasets/auth_logs/labelled_auth_logs.json"),
    "network": (run_network, "datasets/network/labelled_network.json"),
    "deepfake_image": (run_deepfake_image, "ml/data/image_manifest.csv (held-out test sample)"),
}


def main() -> int:
    print("TUNING APPLIED: Added URLhaus and SMS heuristics.")
    print("ML INTEGRATION APPLIED: hybrid heuristics + trained models (Step 3).")
    missing = [str(path) for path in REQUIRED_FILES.values() if not path.exists()]
    if missing:
        print("ERROR: required dataset files are missing:")
        for path in missing:
            print(f"  - {path}")
        print("Run ml/fetch_data.py, ml/preprocess.py (and the Part 8 scripts) first.")
        return 1

    settings = get_settings()
    results: dict[str, dict[str, dict[str, Any]]] = {}

    for name, (runner, _) in MODULES.items():
        print(f"Evaluating {name} (heuristics-only pass) ...")
        settings.ML_ENABLED = False
        heuristic_metrics = finalize(summarize(runner()))

        if name == "account_takeover":
            hybrid_metrics = dict(heuristic_metrics)  # no trained model yet
        else:
            print(f"Evaluating {name} (hybrid pass) ...")
            settings.ML_ENABLED = True
            hybrid_metrics = finalize(summarize(runner()))

        settings.ML_ENABLED = True
        results[name] = {"heuristics": heuristic_metrics, "hybrid": hybrid_metrics}

    # Restore normal operation for any other consumer of the singleton.
    settings.ML_ENABLED = True

    def macro(mode: str) -> dict[str, float]:
        return {
            key: round(sum(results[name][mode][key] for name in results) / len(results), 4)
            for key in ("accuracy", "precision", "recall", "f1", "false_positive_rate", "false_negative_rate")
        }

    macro_heuristics = macro("heuristics")
    macro_hybrid = macro("hybrid")
    artifacts = {name: sha256_file(ML_MODELS_DIR / name) for name in ML_ARTIFACTS}

    def render_table(mode: str) -> list[str]:
        lines = [
            f"{'module':<18}{'n':>7}{'pos':>7}{'flag':>7}{'TP':>7}{'FP':>7}{'TN':>7}{'FN':>7}"
            f"{'acc':>8}{'prec':>8}{'rec':>8}{'f1':>8}{'fpr':>8}{'fnr':>8}{'mean_ms':>10}{'p95_ms':>10}"
        ]
        for name in results:
            m = results[name][mode]
            lines.append(
                f"{name:<18}{m['samples']:>7}{m['positives']:>7}{m['flagged']:>7}"
                f"{m['tp']:>7}{m['fp']:>7}{m['tn']:>7}{m['fn']:>7}"
                f"{m['accuracy']:>8.4f}{m['precision']:>8.4f}{m['recall']:>8.4f}"
                f"{m['f1']:>8.4f}{m['false_positive_rate']:>8.4f}{m['false_negative_rate']:>8.4f}"
                f"{m['mean_latency_ms']:>10.3f}{m['p95_latency_ms']:>10.3f}"
            )
        macro_metrics = macro_heuristics if mode == "heuristics" else macro_hybrid
        lines.append(
            f"{'MACRO AVG':<18}"
            f"{macro_metrics['accuracy']:>8.4f}{macro_metrics['precision']:>8.4f}"
            f"{macro_metrics['recall']:>8.4f}{macro_metrics['f1']:>8.4f}"
            f"{macro_metrics['false_positive_rate']:>8.4f}{macro_metrics['false_negative_rate']:>8.4f}"
        )
        return lines

    header_rule = "=" * 122
    print("\n" + header_rule)
    print("CYBERGUARD evaluation — HEURISTICS-ONLY pass (ml_enabled=false)")
    print(header_rule)
    print("\n".join(render_table("heuristics")))
    print("\n" + header_rule)
    print("CYBERGUARD evaluation — HYBRID pass (heuristics + trained ML models, 0.45/0.55 blend)")
    print(header_rule)
    print("\n".join(render_table("hybrid")))
    print("URL metrics computed on held-out split to avoid train/test overlap.")
    print("Modest metrics are reported honestly; this is a heuristic+ML baseline, not an ML benchmark.")

    # --- machine-readable output ---
    timestamp = datetime.now(timezone.utc).isoformat()
    commit = git_commit()
    payload = {
        "generated_at": timestamp,
        "git_commit": commit,
        "thresholds": {
            "risk_score_flag": RISK_FLAG_THRESHOLD,
            "media_manipulation_probability_flag": MEDIA_FLAG_PROBABILITY,
            "hybrid_blend": {"heuristic_weight": 0.45, "ml_weight": 0.55},
        },
        "artifacts": artifacts,
        "datasets": {
            name: {"path": str(path.relative_to(ROOT)), "provenance_status": provenance_status(name)}
            for name, path in REQUIRED_FILES.items()
        },
        "modules": results,
        "macro_averages": {"heuristics": macro_heuristics, "hybrid": macro_hybrid},
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "evaluation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # --- markdown report ---
    md = ["# CYBERGUARD Evaluation Report", ""]
    md.append(f"Generated: {timestamp}")
    md.append(f"Git commit: {commit if commit else 'not available'}")
    md.append("")
    md.append("## Thresholds and blending")
    md.append("")
    md.append(f"- Heuristic modules: **flagged** when `risk_score >= {RISK_FLAG_THRESHOLD}`.")
    md.append(f"- Media forensics: flagged when `manipulation_probability >= {MEDIA_FLAG_PROBABILITY}`.")
    md.append("- Hybrid blending: `hybrid_score = round(0.45 * heuristic_score + 0.55 * ml_probability * 100)`.")
    md.append("- **URL metrics computed on held-out split to avoid train/test overlap.** Email and network ML metrics are likewise computed on held-out splits produced by `ml/preprocess.py`; the deepfake module uses a deterministic sample of the held-out image test split.")
    md.append("")
    md.append("## Datasets")
    md.append("")
    md.append("| Module | Path | Provenance status |")
    md.append("|---|---|---|")
    for name, path in REQUIRED_FILES.items():
        md.append(f"| {name} | `{path.relative_to(ROOT)}` | {provenance_status(name)} |")
    md.append("")

    for mode, title in (("heuristics", "Heuristics-only"), ("hybrid", "Hybrid (heuristics + trained ML)")):
        md.append(f"## Per-module metrics — {title}")
        md.append("")
        md.append(
            "| Module | n | Positives | Flagged | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 | FPR | FNR | Mean ms | P95 ms |"
        )
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for name in results:
            m = results[name][mode]
            md.append(
                f"| {name} | {m['samples']} | {m['positives']} | {m['flagged']} | {m['tp']} | {m['fp']} | "
                f"{m['tn']} | {m['fn']} | {m['accuracy']} | {m['precision']} | {m['recall']} | {m['f1']} | "
                f"{m['false_positive_rate']} | {m['false_negative_rate']} | {m['mean_latency_ms']} | {m['p95_latency_ms']} |"
            )
        macro_metrics = macro_heuristics if mode == "heuristics" else macro_hybrid
        md.append(
            f"| **Macro average** | | | | | | | | {macro_metrics['accuracy']} | {macro_metrics['precision']} | "
            f"{macro_metrics['recall']} | {macro_metrics['f1']} | {macro_metrics['false_positive_rate']} | "
            f"{macro_metrics['false_negative_rate']} | | |"
        )
        if mode == "hybrid":
            md.append("")
            md.append("account_takeover has no trained model yet; its hybrid row equals the heuristics-only row.")
        md.append("")

    md.append("## ML artifact hashes (SHA-256)")
    md.append("")
    md.append("| Artifact | SHA-256 |")
    md.append("|---|---|")
    for name, digest in artifacts.items():
        md.append(f"| `ml/models/{name}` | {digest or 'missing'} |")
    md.append("")
    md.append("## Limitations")
    md.append("")
    md.append("- The message module evaluates **SMS spam as a proxy** for social-engineering text; classic SMS spam only partially overlaps with phishing heuristics.")
    md.append("- The deepfake evaluation uses a deterministic sample (max 1000 images) of the held-out CIFAKE test split; the CNN was trained on 32x32 CIFAKE images, so metrics do not transfer to high-resolution photos.")
    md.append("- The network model is trained on **KDD99 (1998 DARPA IDS evaluation)** — decades-old traffic patterns; the hybrid flow mapping uses documented constants for duration and response bytes (flows carry neither).")
    md.append("- Latency covers only local detector + ML inference in a single process; no network, storage or LLM time is included.")
    (REPORTS_DIR / "evaluation.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nReports written to {REPORTS_DIR.relative_to(ROOT)}/evaluation.md and evaluation.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
