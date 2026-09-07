"""Preprocess raw ML data into clean train/test splits (ML Step 1).

Reads the raw files produced by ml/fetch_data.py (plus the Part 8 URL
datasets) and writes:

  1. Emails  : ml/data/train_emails.csv / test_emails.csv   (clean_text, label)
  2. URLs    : ml/data/train_urls.csv  / test_urls.csv      (url, label)
  3. Images  : ml/data/images/{train,test}/{real,fake}/ + ml/data/image_manifest.csv
  4. Network : ml/data/train_network.csv / test_network.csv (scaled features, label)
               + fitted StandardScaler at ml/models/network_scaler.pkl (joblib)

Missing raw files are skipped with a warning. All splits use an 80/20 ratio
with a fixed random_state=42 for reproducibility.

Run from the backend directory:
    python ml/preprocess.py
"""

import re
import shutil
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
PROJECT_ROOT = ML_DIR.parents[1]
SEED = 42
TEST_SIZE = 0.2

EMAIL_CLEAN_TAGS = re.compile(r"<[^>]+>")
EMAIL_CLEAN_WHITESPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Lowercase, strip HTML tags and collapse whitespace."""
    text = EMAIL_CLEAN_TAGS.sub(" ", text.lower())
    return EMAIL_CLEAN_WHITESPACE.sub(" ", text).strip()


def warn_missing(path: Path) -> None:
    print(f"WARNING: {path.name} not found — skipping this dataset "
          "(was ml/fetch_data.py run?)")


# ---------------------------------------------------------------------------
# 1. NLP preprocessing (emails)
# ---------------------------------------------------------------------------

def preprocess_emails() -> str:
    raw_path = DATA_DIR / "raw_emails.csv"
    if not raw_path.exists():
        warn_missing(raw_path)
        return "skipped (no raw data)"
    frame = pd.read_csv(raw_path).dropna()
    frame["clean_text"] = frame["text"].astype(str).map(clean_text)
    frame = frame[frame["clean_text"].str.len() > 0][["clean_text", "label"]]
    train, test = train_test_split(
        frame, test_size=TEST_SIZE, random_state=SEED, stratify=frame["label"]
    )
    train.to_csv(DATA_DIR / "train_emails.csv", index=False)
    test.to_csv(DATA_DIR / "test_emails.csv", index=False)
    return f"train={len(train)} test={len(test)} (phishing={int(frame['label'].sum())}, benign={int((frame['label'] == 0).sum())})"


# ---------------------------------------------------------------------------
# 2. URL preprocessing (Part 8 datasets)
# ---------------------------------------------------------------------------

def preprocess_urls() -> str:
    malicious = PROJECT_ROOT / "datasets" / "urls" / "malicious_urls.csv"
    benign = PROJECT_ROOT / "datasets" / "urls" / "benign_urls.csv"
    if not malicious.exists() or not benign.exists():
        warn_missing(malicious if not malicious.exists() else benign)
        return "skipped (no raw data)"

    frame = pd.concat(
        [pd.read_csv(malicious), pd.read_csv(benign)], ignore_index=True
    ).dropna()
    frame = frame.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    train, test = train_test_split(
        frame, test_size=TEST_SIZE, random_state=SEED, stratify=frame["label"]
    )
    train.to_csv(DATA_DIR / "train_urls.csv", index=False)
    test.to_csv(DATA_DIR / "test_urls.csv", index=False)
    return f"train={len(train)} test={len(test)} (malicious={int((frame['label'] == 'malicious').sum())}, benign={int((frame['label'] == 'benign').sum())})"


# ---------------------------------------------------------------------------
# 3. Image preprocessing (deepfake)
# ---------------------------------------------------------------------------

def preprocess_images() -> str:
    raw_path = DATA_DIR / "raw_images.csv"
    if not raw_path.exists():
        warn_missing(raw_path)
        return "skipped (no raw data)"

    frame = pd.read_csv(raw_path).dropna()
    frame["label_name"] = frame["label"].map({0: "real", 1: "fake"})
    train, test = train_test_split(
        frame, test_size=TEST_SIZE, random_state=SEED, stratify=frame["label"]
    )

    images_dir = DATA_DIR / "images"
    manifest = []
    for split_name, split_frame in (("train", train), ("test", test)):
        for _, row in split_frame.iterrows():
            source = DATA_DIR / row["file_path"]
            destination_dir = images_dir / split_name / row["label_name"]
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / Path(row["file_path"]).name
            if not destination.exists():
                shutil.copy2(source, destination)
            manifest.append(
                {
                    "file_path": str(destination.relative_to(PROJECT_ROOT)),
                    "label": row["label_name"],
                    "split": split_name,
                }
            )

    manifest_path = DATA_DIR / "image_manifest.csv"
    pd.DataFrame(manifest).to_csv(manifest_path, index=False)
    counts = pd.DataFrame(manifest).groupby(["split", "label"]).size().to_dict()
    return f"manifest={len(manifest)} images; counts={counts}"


# ---------------------------------------------------------------------------
# 4. Network preprocessing
# ---------------------------------------------------------------------------

def preprocess_network() -> str:
    raw_path = DATA_DIR / "raw_network.csv"
    if not raw_path.exists():
        warn_missing(raw_path)
        return "skipped (no raw data)"

    frame = pd.read_csv(raw_path)
    frame = frame.dropna()
    label = frame["label"].map(lambda value: str(value).rstrip("."))
    features = frame.drop(columns=["label"])

    for column in features.columns:
        if not pd.api.types.is_numeric_dtype(features[column]):
            try:
                features[column] = pd.to_numeric(features[column])
            except (ValueError, TypeError):
                features[column] = LabelEncoder().fit_transform(features[column].astype(str))

    scaler = StandardScaler()
    scaled = pd.DataFrame(
        scaler.fit_transform(features), columns=features.columns, index=features.index
    )
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, MODELS_DIR / "network_scaler.pkl")

    result = scaled.assign(label=label.values)
    try:
        train, test = train_test_split(
            result, test_size=TEST_SIZE, random_state=SEED, stratify=result["label"]
        )
    except ValueError:
        # Rare KDD classes with a single member cannot be stratified.
        train, test = train_test_split(result, test_size=TEST_SIZE, random_state=SEED)
    train.to_csv(DATA_DIR / "train_network.csv", index=False)
    test.to_csv(DATA_DIR / "test_network.csv", index=False)
    return (
        f"train={len(train)} test={len(test)} features={len(features.columns)} "
        f"classes={sorted(set(label))[:6]}{'...' if label.nunique() > 6 else ''}"
    )


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    steps = [
        ("emails (NLP)", preprocess_emails),
        ("urls", preprocess_urls),
        ("images (deepfake)", preprocess_images),
        ("network", preprocess_network),
    ]

    print("=== Preprocessing summary (80/20 splits, random_state=42) ===")
    for name, runner in steps:
        try:
            print(f"{name:<20} {runner()}")
        except Exception as exc:
            print(f"{name:<20} FAILED: {exc}")

    print(f"\nModel weights directory: {MODELS_DIR.relative_to(PROJECT_ROOT)}/ (empty, ready for training)")
    print("Clean splits are in ml/data/; next step can train models with scikit-learn/XGBoost/torch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
