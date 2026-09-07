"""Fetch public cybersecurity datasets for ML training (ML Step 1).

Sources (no API keys required):
  1. Phishing emails : HF dataset "pirocheto/phishing-email"  -> ml/data/raw_emails.csv
  2. Deepfake images : HF dataset "abidlabs/cifake" (fallback "nateraw/cifake"),
     'train' split only (the large test split is skipped on purpose)
                       -> images + ml/data/raw_images.csv
  3. Network traffic : sklearn.datasets.fetch_kddcup99(subset=True)
                       -> ml/data/raw_network.csv

Every download is wrapped in try/except: a failure is logged and skipped so
ml/preprocess.py can handle missing raw files gracefully.

Run from the backend directory:
    python ml/fetch_data.py
"""

import csv
import sys
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
IMAGES_RAW_DIR = DATA_DIR / "images_raw"

PHISHING_DATASET_IDS = [
    ("pirocheto/phishing-email", None),  # primary (spec); gated on the Hub -> 401 without login
    ("cybersectony/PhishingEmailDetectionv2.0", None),  # ungated fallback mirror
    ("ealvaradob/phishing-dataset", "emails"),  # legacy loading script (needs datasets<3.0)
]
CIFAKE_DATASET_IDS = [
    "abidlabs/cifake",  # primary (spec)
    "nateraw/cifake",  # fallback (spec)
    "dragonintelligence/CIFAKE-image-dataset",  # ungated fallback mirror (train/test parquet)
]

# KDDCup-99 full feature layout (used when all 41 columns are present).
KDD99_COLUMNS = [
    "duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes",
    "land", "wrong_fragment", "urgent", "hot", "num_failed_logins", "logged_in",
    "num_compromised", "root_shell", "su_attempted", "num_root",
    "num_file_creations", "num_shells", "num_access_files", "num_outbound_cmds",
    "is_host_login", "is_guest_login", "count", "srv_count", "serror_rate",
    "srv_serror_rate", "rerror_rate", "srv_rerror_rate", "same_srv_rate",
    "diff_srv_rate", "srv_diff_host_rate", "dst_host_count",
    "dst_host_srv_count", "dst_host_same_srv_rate", "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate", "dst_host_srv_diff_host_rate",
    "dst_host_serror_rate", "dst_host_srv_serror_rate", "dst_host_rerror_rate",
    "dst_host_srv_rerror_rate",
]


def write_csv(path: Path, header: list[str], rows) -> None:
    """Write atomically: a mid-write failure cannot leave a partial CSV behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    try:
        with tmp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def decode(value) -> str:
    """KDDCup-99 ships byte strings; normalise to plain str."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def pd_read_rows(path: Path) -> list:
    """Count rows of an existing raw CSV without loading it into pandas."""
    import csv as _csv

    with path.open(newline="", encoding="utf-8") as handle:
        return list(_csv.DictReader(handle))


def normalize_label(value) -> int:
    """Coerce dataset-specific labels to 0 (benign) / 1 (phishing or fake).

    Multi-class security datasets (e.g. cybersectony's safe/phishing/fraud)
    collapse to benign vs malicious: class 0 is benign, anything else malicious.
    """
    if isinstance(value, str):
        mapping = {
            "phishing": 1, "spam": 1, "smishing": 1, "malicious": 1, "fake": 1,
            "benign": 0, "ham": 0, "legitimate": 0, "real": 0, "normal": 0,
        }
        return mapping[value.strip().lower()]
    return 0 if int(value) == 0 else 1


def _already_fetched(path: Path) -> bool:
    if path.exists():
        print(f"  OK: {path.name} already present, skipping download (delete it to re-fetch).")
        return True
    return False


def fetch_phishing_emails() -> int:
    if _already_fetched(DATA_DIR / "raw_emails.csv"):
        return len(pd_read_rows(DATA_DIR / "raw_emails.csv"))
    from datasets import load_dataset

    split_frame = None
    used_id = None
    for dataset_id, config in PHISHING_DATASET_IDS:
        try:
            suffix = f" (config '{config}')" if config else ""
            print(f"Fetching phishing emails from '{dataset_id}'{suffix} ...")
            dataset = load_dataset(dataset_id, config) if config else load_dataset(dataset_id)
            split_frame = dataset["train"] if "train" in dataset else next(iter(dataset.values()))
            used_id = dataset_id
            break
        except Exception as exc:  # gated dataset, HF downtime, network issue
            print(f"  WARNING: could not load '{dataset_id}': {exc}")
    if split_frame is None:
        print("  WARNING: all phishing-email sources failed; email data will be missing.")
        return 0

    text_column = next(
        (name for name in ("text", "content", "email", "body", "message") if name in split_frame.column_names),
        None,
    )
    if text_column is None:
        print(f"  WARNING: no text column found in '{used_id}' (columns: {split_frame.column_names}).")
        return 0

    rows = ((str(item[text_column]), normalize_label(item["label"])) for item in split_frame)
    write_csv(DATA_DIR / "raw_emails.csv", ["text", "label"], rows)
    print(f"  OK: {len(split_frame)} emails from '{used_id}' (text column: '{text_column}') -> ml/data/raw_emails.csv")
    return len(split_frame)


def fetch_deepfake_images() -> int:
    if _already_fetched(DATA_DIR / "raw_images.csv"):
        return len(pd_read_rows(DATA_DIR / "raw_images.csv"))
    from datasets import load_dataset

    dataset = None
    used_id = None
    for dataset_id in CIFAKE_DATASET_IDS:
        try:
            print(f"Fetching deepfake images from '{dataset_id}' (train split only) ...")
            dataset = load_dataset(dataset_id, split="train")
            used_id = dataset_id
            break
        except Exception as exc:  # HF downtime, dataset rename, network issue
            print(f"  WARNING: could not load '{dataset_id}': {exc}")
    if dataset is None:
        print("  WARNING: all CIFAKE sources failed; image data will be missing.")
        return 0

    IMAGES_RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, item in enumerate(dataset):
        image = item["image"]
        label = normalize_label(item["label"])  # CIFAKE: 0 = real, 1 = fake (AI-generated)
        file_name = f"img_{index:06d}.png"
        image.save(IMAGES_RAW_DIR / file_name)
        rows.append([f"images_raw/{file_name}", label])

    write_csv(DATA_DIR / "raw_images.csv", ["file_path", "label"], rows)
    print(f"  OK: {len(rows)} images from '{used_id}' -> ml/data/images_raw/ + ml/data/raw_images.csv")
    return len(rows)


def fetch_network_traffic() -> int:
    if _already_fetched(DATA_DIR / "raw_network.csv"):
        return len(pd_read_rows(DATA_DIR / "raw_network.csv"))
    from sklearn.datasets import fetch_kddcup99

    print("Fetching network traffic via sklearn fetch_kddcup99(subset='SF') ...")
    bunch = fetch_kddcup99(subset="SF")
    data, target = bunch.data, bunch.target

    rows = []
    for record, label in zip(data, target):
        rows.append([decode(value) for value in record] + [decode(label)])

    n_features = len(rows[0]) - 1 if rows else 0
    columns = KDD99_COLUMNS if n_features == len(KDD99_COLUMNS) else [f"f{i}" for i in range(n_features)]
    write_csv(DATA_DIR / "raw_network.csv", columns + ["label"], rows)
    print(f"  OK: {len(rows)} flows ({n_features} features) -> ml/data/raw_network.csv")
    return len(rows)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    for name, fetcher in (
        ("phishing_emails", fetch_phishing_emails),
        ("deepfake_images", fetch_deepfake_images),
        ("network_traffic", fetch_network_traffic),
    ):
        try:
            count = fetcher()
            summary.append((name, count if count else "skipped/empty"))
        except Exception as exc:
            print(f"  WARNING: '{name}' fetch failed, skipping: {exc}")
            summary.append((name, "FAILED (skipped)"))

    print("\n=== Fetch summary ===")
    print(f"{'dataset':<20}{'rows/images':>16}")
    print("-" * 36)
    for name, count in summary:
        print(f"{name:<20}{str(count):>16}")
    print("\nRaw files are in ml/data/; run python ml/preprocess.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
